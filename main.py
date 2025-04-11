import re

import aiohttp
from data.plugins.astrbot_plugin_gallery.core.ocr_sever import ocr
from data.plugins.astrbot_plugin_gallery.core.parse import get_image_info

from .core.emoji import emoji_list
from astrbot import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
import astrbot.core.message.components as Comp
from astrbot.core.platform import AstrMessageEvent
import random
from pathlib import Path

from astrbot.core.star.filter.event_message_type import EventMessageType
from data.plugins.astrbot_plugin_gallery.core.gallery import Gallery, GalleryManager

# 图库数据存储路径
GALLERIES_DIR = Path("data/plugins_data") / "astrbot_plugin_gallery"

# 存储图库信息的 JSON 文件
GALLERIES_INFO_FILE = Path("data/plugins_data") / "astrbot_plugin_gallery_info.json"


@register(
    "astrbot_plugin_gallery",
    "Zhalslar",
    "复读插件",
    "1.0.0",
    "https://github.com/Zhalslar/astrbot_plugin_gallery",
)
class GalleryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 用户消息长度不超过此长度时不响应
        self.min_msg_length: int = config.get("min_msg_length", 1)
        # 用户消息长度超过此长度时不响应
        self.max_msg_length: int = config.get("max_msg_length", 20)
        # 下载图片时是否压缩图片，默认开启
        self.default_compress_switch: bool = config.get("default_compress_switch", True)
        # 压缩阈值(单位为像素)，图片在512像素以下时qq以表情包大小显示
        self.compress_size: int = config.get("compress_size", 512)
        # 添加图片时是否检查并跳过重复图片
        self.default_duplicate_switch: bool = config.get("default_duplicate_switch", True)
        # 是否默认模糊匹配
        self.default_fuzzy_match: bool = config.get("default_fuzzy_match", False)
        # 精准匹配时发送图片的概率
        self.exact_match_prob: float = config.get("exact_match_prob", 0.9)
        # 模糊匹配时发送图片的概率
        self.fuzzy_match_prob: float = config.get("fuzzy_match_prob", 0.9)
        # 允许的图库名、图片名的最大长度(汉字为单位，一个字母相当于0.5714个汉字)
        self.label_max_length: int = config.get("label_max_length", 4)
        # 每个图库的图片最大保存量
        self.max_pic_count: int = config.get("max_pic_count", 200)
        # 初始化总图库文件夹
        self.gm = GalleryManager(GALLERIES_DIR, GALLERIES_INFO_FILE)
        logger.info("图库插件初始化完成")

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_match(self, event: AstrMessageEvent):
        message_str = event.get_message_str()
        if self.min_msg_length < len(message_str) < self.max_msg_length:
            # 精准匹配
            if message_str in self.gm.get_exact_match_keywords():
                if random.random() < self.exact_match_prob:
                    galleris = self.gm.get_gallery_by_keyword(message_str)
                    gallery = random.choice(galleris)
                    image_path = gallery.get_random_image()
                    yield event.image_result(str(image_path))

            # 模糊匹配
            for keyword in self.gm.get_fuzzy_match_keywords():
                if keyword in message_str:
                    if random.random() < self.fuzzy_match_prob:
                        galleris = self.gm.get_gallery_by_keyword(keyword)
                        gallery = random.choice(galleris)
                        image_path = gallery.get_random_image()
                        yield event.image_result(str(image_path))


    @filter.command("精准匹配词")
    async def list_accurate_keywords(self, event: AstrMessageEvent):
        reply = f"【精准匹配词】：\n{str(self.gm.get_exact_match_keywords())}"
        yield event.plain_result(reply)

    @filter.command("模糊匹配词")
    async def list_fuzzy_keywords(self, event: AstrMessageEvent):
        reply = f"【模糊匹配词】：\n{str(self.gm.get_fuzzy_match_keywords())}"
        yield event.plain_result(reply)

    @filter.command("添加匹配词")
    async def add_ketord(
        self,
        event: AstrMessageEvent,
        keyword: str | None = None,
        gallery_name: str | None = None,
    ):
        gallery = await self.get_gallary(event, gallery_name)
        if not gallery:
            yield event.plain_result("未找到对应图库")
            return
        if not keyword:
            yield event.plain_result("未指定匹配词")
            return
        result = gallery.add_keyword(keyword)
        yield event.plain_result(result)

    @filter.command("删除匹配词")
    async def delete_keyword(
        self,
        event: AstrMessageEvent,
        keyword: str | None = None,
        gallery_name: str | None = None,
    ):
        gallery = await self.get_gallary(event, gallery_name)
        if not gallery:
            yield event.plain_result("未找到对应图库")
            return
        if not keyword:
            yield event.plain_result("未指定匹配词")
            return
        result = gallery.delete_keyword(keyword)
        yield event.plain_result(result)


    @filter.command("图库列表")
    async def list_galleries(self, event: AstrMessageEvent):
        """查看图库列表"""
        galleries = self.gm.galleries
        if not galleries:
            yield event.plain_result("未创建任何图库")
            return
        galleries_str = "\n\n\n".join(
            [galleries[gallery_key].__str__() for gallery_key in galleries]
        )
        yield event.plain_result(galleries_str)

    @filter.command("保存", alias={"存图", "偷图"})
    async def save_image(
        self, event: AstrMessageEvent, gallery_name: str | None = None
    ):
        "保存图片到图库中"
        label = await self.get_label(event) or "Unknown"
        gallery_name = gallery_name or label or "Unknown"
        gallery_info = {
            "name": gallery_name,
            "creator_id": event.get_sender_id(),
            "creator_name": event.get_sender_name(),
            "password": "114514",
            "max_capacity": self.max_pic_count,
            "compress_switch": self.default_compress_switch,
            "duplicate_switch": self.default_duplicate_switch,
            "fuzzy_match": self.default_fuzzy_match,
        }
        gallery = self.gm.add_gallery(gallery_info) or self.gm.get_gallery(gallery_name)
        if not gallery:
            yield event.plain_result("未找到对应图库")
            return
        image = await self.get_image(event)
        if not image:
            yield event.plain_result("未找到任何图片")
            return
        result = gallery.add_image(image_bytes=image, image_label=label)
        yield event.plain_result(result)

    # @filter.command("替换")
    # async def replace(self, event: AstrMessageEvent):

    # @filter.command("添图")
    # async def add(self, event: AstrMessageEvent):

    # @filter.command("批量添图")
    # async def adds(self, event: AstrMessageEvent):

    @filter.command("删除图库")
    async def delete_gallery(
        self, event: AstrMessageEvent, gallery_name: str | None = None
    ):
        """删除图库"""
        label = await self.get_label(event)
        gallery_name = gallery_name or label or "Unknown"
        is_deleted = self.gm.delete_gallery(gallery_name)
        if is_deleted:
            yield event.plain_result(f"已删除图库【{gallery_name}】")
        else:
            yield event.plain_result("删除失败")

    @filter.command("删图", alias={"删除图片"})
    async def delete_image(
        self,
        event: AstrMessageEvent,
        index: int | None = None,
        gallery_name: str | None = None,
    ):
        """删除图库的指定序号图片"""
        gallery = await self.get_gallary(event, gallery_name)
        if not gallery:
            yield event.plain_result("未找到对应图库")
            return
        if not index:
            yield event.plain_result("未指定图片序号")
            return
        result = gallery.delete_image_by_index(index)
        yield event.plain_result(result)

    # @filter.command("批量删图")
    # async def deletes(self, event: AstrMessageEvent):

    @filter.command("查看")
    async def view_image(
        self,
        event: AstrMessageEvent,
        index: str | None = None,
        gallery_name: str | None = None,
    ):
        """查看图库里的指定序号图片"""
        gallery = await self.get_gallary(event, gallery_name)
        if not gallery:
            yield event.plain_result("未找到对应图库")
            return
        if not index:
            yield event.plain_result("未指定图片序号")
            return
        result = gallery.view_by_index(index)
        if isinstance(result, str):
            yield event.plain_result(result)
            return
        yield event.image_result(str(result))

    @filter.command("预览", alias={"预览图库", "查看图库"})
    async def preview_gallery(
        self, event: AstrMessageEvent, gallery_name: str | None = None
    ):
        """预览图库"""
        gallery = await self.get_gallary(event, gallery_name)
        if not gallery:
            yield event.plain_result("未找到对应图库")
            return
        result = gallery.preview()
        if isinstance(result, str):
            yield event.plain_result(result)
            return
        chain = [Comp.Image.fromBytes(result)]
        yield event.chain_result(chain)  # type: ignore

    @filter.command("图库详情")
    async def gallery_details(
        self, event: AstrMessageEvent, gallery_name: str | None = None
    ):
        """查看图库的详细信息"""
        gallery = await self.get_gallary(event, gallery_name)
        if not gallery:
            yield event.plain_result("未找到对应图库")
            return
        details = gallery.__str__()
        yield event.plain_result(details)

    @filter.command("路径")
    async def find_path(self, event: AstrMessageEvent, gallery_name: str | None = None):
        """查看图库路径"""
        gallery = await self.get_gallary(event, gallery_name)
        if not gallery:
            yield event.plain_result("未找到对应图库")
            return
        image = await self.get_image(event)
        if not image:
            yield event.plain_result("未指定要查找的图片")
            return
        image_name = gallery.view_by_bytes(image=image)
        yield event.plain_result(f"{image_name}")

    @filter.command("解析")
    async def parse(self, event: AstrMessageEvent):
        """解析图片的信息"""
        image = await self.get_image(event)
        if not image:
            yield event.plain_result("未指定要解析的图片")
            return
        info_str = await get_image_info(image)
        if not info_str:
            yield event.plain_result("解析失败")
            return
        yield event.plain_result(info_str)

    @filter.command("提取")
    async def image_ocr(self, event: AstrMessageEvent):
        """提取图片的文字"""
        image = await self.get_image(event)
        if not image:
            yield event.plain_result("未指定要提取的图片")
            return
        text = await ocr(image)
        if not text:
            yield event.plain_result("提取失败")
            return
        cleaned_text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", text)
        yield event.plain_result(cleaned_text)

    @staticmethod
    async def download_image(url: str) -> bytes | None:
        """下载图片"""
        url = url.replace("https://", "http://")
        try:
            async with aiohttp.ClientSession() as client:
                response = await client.get(url)
                img_bytes = await response.read()
                return img_bytes
        except Exception as e:
            logger.error(f"图片下载失败: {e}")

    async def get_label(self, event: AstrMessageEvent) -> str | None:
        """获取@者的标签"""
        label = None
        # 获取@者的QQ号
        messages = event.get_messages()
        self_id = event.get_self_id()
        target_id = next(
            (
                str(seg.qq)
                for seg in messages
                if (isinstance(seg, Comp.At)) and str(seg.qq) != self_id
            ),
            None,
        )

        # aiocqhttp获取@者昵称
        if target_id and event.get_platform_name() == "aiocqhttp":
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )

            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot
            user_info = await client.get_stranger_info(user_id=int(target_id))
            label = user_info.get("nickname")
        # 如果没有@者，使用发送者的昵称
        if label is None:
            send_name = event.get_sender_name()
            label = send_name

        # 过滤掉emoji和中文字符
        pattern = r"[\u4e00-\u9fa5]"

        filtered_chars = [
            char
            for char in label
            if char in emoji_list or re.match(pattern, char) or char.isalnum()
        ]

        last_char = filtered_chars.pop() if filtered_chars else ""

        result = []
        current_weight = 0
        weight_per_letter_digit = 4 / 7  # 每个字母或数字的权重

        for char in filtered_chars:
            weight = (
                1
                if char in emoji_list or re.match(pattern, char)
                else weight_per_letter_digit
            )
            if current_weight + weight > self.label_max_length:
                break
            result.append(char)
            current_weight += weight

        result.append(last_char)
        return "".join(result)

    async def get_image(self, event: AstrMessageEvent) -> bytes | None:
        """获取图片"""
        chain = event.get_messages()
        # 遍历引用消息
        reply_seg = next((seg for seg in chain if isinstance(seg, Comp.Reply)), None)
        if reply_seg and reply_seg.chain:
            for seg in reply_seg.chain:
                if isinstance(seg, Comp.Image):
                    if img_url := seg.url:
                        if msg_image := await self.download_image(img_url):
                            return msg_image
        # 遍历原始消息
        for seg in chain:
            if isinstance(seg, Comp.Image):
                if img_url := seg.url:
                    if msg_image := await self.download_image(img_url):
                        return msg_image

    async def get_gallary(
        self, event: AstrMessageEvent, gallery_name: str | None
    ) -> Gallery | None:
        """获取目标图库"""
        label = await self.get_label(event)
        gallery_name = gallery_name or label or "Unknown"
        gallery = self.gm.get_gallery(gallery_name)
        return gallery

