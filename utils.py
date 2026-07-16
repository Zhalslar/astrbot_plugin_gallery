
import io
import os
import re

import aiohttp
from PIL import Image as PILImage

from astrbot import logger
from astrbot.core.message.components import At, Image, Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.session_waiter import SessionController, session_waiter

HELP_TEXT = (
    "【图库帮助】(标有s表示可输入多个,空格隔开参数,图库名皆可用@某人代替)\n\n"
    "图库版本 - 查看插件版本信息\n\n"
    "精准匹配词 - 查看精准匹配的图库及其匹配词\n\n"
    "模糊匹配词 - 查看模糊匹配的图库及其匹配词\n\n"
    "模糊匹配 <图库名s> - 将指定图库切换到模糊匹配模式\n\n"
    "精准匹配 <图库名s> - 将指定图库切换到精准匹配模式\n\n"
    "添加匹配词 <图库名> <匹配词s> - 为指定图库添加匹配词\n\n"
    "删除匹配词 <图库名> <匹配词s> - 为指定图库删除匹配词\n\n"
    "设置别称 <图库名> <别称s> - 设置图库的别称（覆盖原别称）\n\n"
    "添加别称 <图库名> <别称s> - 为图库添加别称\n\n"
    "删除别称 <图库名> <别称s> - 为图库删除别称\n\n"
    "设置容量 <图库名> <容量> - 设置指定图库的容量上限\n\n"
    "开启压缩 <图库名s> - 打开指定图库的压缩开关\n\n"
    "关闭压缩 <图库名s> - 关闭指定图库的压缩开关\n\n"
    "开启去重 <图库名s> - 打开指定图库的去重开关\n\n"
    "关闭去重 <图库名s> - 关闭指定图库的去重开关\n\n"
    "去重 <图库名s> - 去除图库里重复的图片\n\n"
    "存图 <图库名> <序号> - 存图到指定图库，序号指定时会替换掉原图，图库名不填则默认自己昵称，也可@他人作为图库名\n\n"
    "删图 <图库名> <序号s> - 删除指定图库中的图片，序号不指定表示删除整个图库\n\n"
    "看图 <序号s/图库名> - 查看指定图库中的图片或图库详情，序号指定时查看单张图片\n\n"
    "图库列表 - 查看所有图库\n\n"
    "图库详情 <图库名s> - 查看指定图库的详细信息\n\n"
    "(引用图片)/路径 <图库名s> - 查看指定图片的路径，需指定在哪个图库查找\n\n"
    "(引用图片)/解析 - 解析图片的信息\n\n"
    "上传图库 <图库名s> - 将图库打包成ZIP上传\n\n"
    "(引用ZIP)下载图库 <图库名> - 下载ZIP重命名后加载为图库"
)

def get_dirs(path: str) ->  list[str]:
    """
    获取指定目录下的所有子目录路径（不包括文件）
    """
    directories = []
    with os.scandir(path) as entries:
        for entry in entries:
            if entry.is_dir():
                directories.append(entry.path)
    return directories


async def download_file(url: str) -> bytes | None:
    """
    下载/读取文件内容为 bytes。
    兼容：http(s) 链接、本地绝对路径、file:// URI、URL 编码的本地路径。
    """
    # 1) 本地路径（含 URL 编码形式，如 c:%5CUsers%5C...）
    decoded = url
    try:
        from urllib.parse import unquote, urlparse

        decoded = unquote(url)
    except Exception:
        pass

    # file:// URI
    if decoded.startswith("file://"):
        try:
            from pathlib import Path
            from urllib.parse import urlparse

            local_path = Path(urlparse(decoded).path).as_posix()
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.error(f"读取本地文件失败（file URI）: {e}")
            return None

    # 裸本地路径（可能是 URL 编码的，如 c:%5CUsers...）
    if os.path.exists(decoded):
        try:
            with open(decoded, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"读取本地文件失败: {e}")
            return None

    # 2) 网络链接（保留原行为，但不再错误地替换 https→http）
    try:
        async with aiohttp.ClientSession() as client:
            response = await client.get(url)
            img_bytes = await response.read()
            return img_bytes
    except Exception as e:
        logger.error(f"文件下载失败: {e}")
        return None


async def get_nickname(event: AstrMessageEvent, target_id: str):
    """从消息平台获取参数"""
    if event.get_platform_name() == "aiocqhttp":
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        assert isinstance(event, AiocqhttpMessageEvent)
        client = event.bot
        user_info = await client.get_stranger_info(user_id=int(target_id))
        return user_info.get("nickname")
    # TODO 适配更多消息平台
    return f"{target_id}"


async def _image_to_bytes(seg: Image) -> bytes | None:
    """
    把一个 Image 组件解析为字节。
    优先用框架的 convert_to_file_path（兼容 http / file URI / base64 / 本地路径），
    失败时回退到 download_file。
    """
    # 1) 优先走框架统一解析（新版 AstrBot 推荐）
    try:
        file_path = await seg.convert_to_file_path()
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as f:
                return f.read()
    except Exception as e:
        logger.debug(f"convert_to_file_path 失败，回退到 download_file: {e}")

    # 2) 回退：直接拿 url/file 去 download_file（已兼容本地路径）
    source = seg.url or seg.file
    if source:
        return await download_file(source)
    return None


async def get_image(
   event: AstrMessageEvent, reply: bool = True, get_url: bool = False
) -> bytes | str | None:
    """获取图片"""
    chain = event.get_messages()
    # 遍历引用消息
    if reply:
        reply_seg = next(
            (seg for seg in chain if isinstance(seg, Reply)), None
        )
        if reply_seg and reply_seg.chain:
            for seg in reply_seg.chain:
                if isinstance(seg, Image):
                    if get_url:  # 获取图片URL（给LLM打标用）
                        if img_url := seg.url or seg.file:
                            return img_url
                    else:
                        if msg_image := await _image_to_bytes(seg):
                            return msg_image
    # 遍历原始消息
    for seg in chain:
        if isinstance(seg, Image):
            if get_url:  # 获取图片URL
                if img_url := seg.url or seg.file:
                    return img_url
            else:
                if msg_image := await _image_to_bytes(seg):
                    return msg_image

def filter_text(text: str, max_length: int = 128) -> str:
    """过滤字符，只保留中文、数字和字母, 并截短非数字字符串"""
    f_str = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", text)
    return f_str if f_str.isdigit() else f_str[:max_length]

async def get_args(event: AstrMessageEvent):
        """获取参数"""
        # 初始化默认值
        sender_id = filter_text(event.get_sender_id())
        sender_name = filter_text(event.get_sender_name())

        # 解析消息文本
        args = event.message_str.strip().split()[1:]
        texts: list[str] = []
        numbers: list[int] = []
        at_names: list[str] = []

        for arg in args:
            if arg.isdigit():
                num = int(arg)
                if 0 < num < 10000:
                    numbers.append(num)  # 满足条件的数字加入 indexs
                else:
                    texts.append(arg)  # 不满足条件的数字加入 texts
            else:  # 如果是文本
                if filtered_arg := filter_text(arg):
                    if arg.startswith("@"):
                        at_names.append(filtered_arg)
                    else:
                        texts.append(filtered_arg)


        # 获取消息链
        chain = event.get_messages().copy()

        # 去除开头的Reply和At
        while chain and (
            isinstance(chain[0], Reply) or isinstance(chain[0], At)
        ):
            chain.pop(0)

        # 获取@列表
        at_ids = [str(seg.qq) for seg in chain if isinstance(seg, At)]

        # 获取回复信息
        reply_seg = next(
            (seg for seg in event.get_messages() if isinstance(seg, Reply)), None
        )
        reply_name = (
            filter_text(await get_nickname(event, str(reply_seg.sender_id)))
            if reply_seg
            else None
        )
        names = at_ids or texts or [sender_id]
        labels = [
            name for name in (at_names, reply_name, sender_name, sender_id) if name
        ]

        # 返回参数字典
        return {
            "texts": texts,
            "numbers": numbers or [0],
            "names": names,
            "labels": labels,
        }


def compress_image(image: bytes, max_size: int = 512) -> bytes | None:
    """压缩图片"""
    try:
        with PILImage.open(io.BytesIO(image)) as img:
            # GIF 不压缩
            if img.format == "GIF":
                return image
            # 尺寸不超过 max_size，不压缩
            if img.width <= max_size and img.height <= max_size:
                return image
            # 执行压缩
            img.thumbnail((max_size, max_size), PILImage.Resampling.LANCZOS)
            output = io.BytesIO()
            img.save(output, format=img.format)
            return output.getvalue()
    except Exception as e:
        logger.error(f"压缩图片失败：{e}")
        return None


# ==================== dhash 近似判重 ====================


def calculate_dhash(image: bytes, hash_size: int = 8) -> str:
    """
    计算图片的感知哈希（dHash）
    
    Args:
        image: 图片字节
        hash_size: 哈希大小，默认 8（生成 64 位哈希）
    
    Returns:
        十六进制哈希字符串
    """
    try:
        with PILImage.open(io.BytesIO(image)) as img:
            # 转灰度
            img = img.convert("L")
            # 缩小为 hash_size x hash_size
            img = img.resize((hash_size + 1, hash_size), PILImage.Resampling.LANCZOS)
            
            # 计算相邻像素差值
            pixels = list(img.getdata())
            difference = []
            for i in range(hash_size):
                for j in range(hash_size):
                    row = i * (hash_size + 1)
                    pixel_left = pixels[row + j]
                    pixel_right = pixels[row + j + 1]
                    difference.append(pixel_left > pixel_right)
            
            # 转十六进制
            decimal_value = 0
            for index, value in enumerate(difference):
                if value:
                    decimal_value += 2 ** index
            
            return hex(decimal_value)[2:].zfill(hash_size * hash_size // 4)
    except Exception as e:
        logger.error(f"计算 dhash 失败：{e}")
        return ""


def hamming_distance(hash1: str, hash2: str) -> int:
    """
    计算两个十六进制哈希的汉明距离
    
    Args:
        hash1, hash2: dhash 字符串
    
    Returns:
        汉明距离（不同比特数）
    """
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return 999  # 无效哈希，返回大距离
    
    # 转二进制再按位比较
    h1 = bin(int(hash1, 16))[2:].zfill(len(hash1) * 4)
    h2 = bin(int(hash2, 16))[2:].zfill(len(hash2) * 4)
    
    return sum(c1 != c2 for c1, c2 in zip(h1, h2))


def is_similar_image(hash1: str, hash2: str, threshold: int = 5) -> bool:
    """
    判断两张图片是否相似（基于 dhash 汉明距离）
    
    Args:
        hash1, hash2: dhash 字符串
        threshold: 相似度阈值（汉明距离 ≤ 此值视为相似）
    
    Returns:
        True 表示相似
    """
    distance = hamming_distance(hash1, hash2)
    return distance <= threshold

