
import re
import aiohttp
import zipfile
import os
import shutil
from astrbot import logger
from astrbot.core.message.components import At, Image, Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent

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
    """下载图片"""
    url = url.replace("https://", "http://")
    try:
        async with aiohttp.ClientSession() as client:
            response = await client.get(url)
            img_bytes = await response.read()
            return img_bytes
    except Exception as e:
        logger.error(f"图片下载失败: {e}")

def unzip_file(zip_path: str, folder_path: str) -> bool:
    """解压压缩包，成功返回True，失败返回False"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(folder_path)
        return True
    except Exception as e:
        logger.error(f"解压文件 {zip_path} 失败: {e}")
        return False


def zip_folder(folder_path: str, zip_path: str) -> bool:
    """压缩文件夹，成功返回True，失败返回False"""
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(
                        file_path, arcname=os.path.relpath(file_path, start=folder_path)
                    )
        return True
    except Exception as e:
        logger.error(f"压缩文件夹 {folder_path} 失败: {e}")
        return False


def move_files_up(directory):
    """
    如果目录下只有一个子文件夹，移动其中的所有文件和子文件夹到上一级目录，并删除该子文件夹。
    递归检查直到不满足条件。
    保持子文件夹内的文件结构。
    """
    while True:
        # 获取目录下所有的子目录和文件
        entries = os.listdir(directory)
        subfolders = [
            entry for entry in entries if os.path.isdir(os.path.join(directory, entry))
        ]

        # 如果只有一个子文件夹
        if len(subfolders) == 1:
            subfolder_path = os.path.join(directory, subfolders[0])

            # 遍历子文件夹中的所有内容并移动到上一级目录
            for root, dirs, files in os.walk(subfolder_path, topdown=False):
                # 移动文件
                for file in files:
                    file_path = os.path.join(root, file)
                    shutil.move(file_path, os.path.join(directory, file))

                # 移动子文件夹
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    shutil.move(dir_path, os.path.join(directory, dir))

            # 删除子文件夹
            shutil.rmtree(subfolder_path)

            # 继续检查上级目录
            continue

        # 如果不是只有一个子文件夹，退出循环
        break


async def get_nickname(event: AstrMessageEvent, target_id: str):
    """从消息平台获取参数"""
    if event.get_platform_name() == "aiocqhttp":
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        assert isinstance(event, AiocqhttpMessageEvent)
        client = event.bot
        user_info = await client.get_stranger_info(user_id=int(target_id))
        nickname = user_info.get("nickname")
        return nickname
    # TODO 适配更多消息平台
    return f"{target_id}"


async def get_image(
   event: AstrMessageEvent, reply: bool = True
) -> bytes | None:
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
                    if img_url := seg.url:
                        if msg_image := await download_file(img_url):
                            return msg_image
    # 遍历原始消息
    for seg in chain:
        if isinstance(seg, Image):
            if img_url := seg.url:
                if msg_image := await download_file(img_url):
                    return msg_image

def filter_text(text: str, max_length: int = 10) -> str:
    """过滤字符，只保留中文、数字和字母, 并截短非数字字符串"""
    f_str = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", text)
    return f_str[: max_length] if not f_str.isdigit() else f_str

async def get_args(event: AstrMessageEvent, cmd: str):
        """获取参数"""
        # 初始化默认值
        sender_id = filter_text(event.get_sender_id())
        sender_name = filter_text(event.get_sender_name())
        message_str = event.message_str

        # 解析消息文本
        args = message_str.removeprefix(cmd).strip().split(" ")
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
                filtered_arg = filter_text(arg)
                if filtered_arg:
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
