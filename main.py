import asyncio
import os
import re
import aiohttp
from typing import Callable, Awaitable
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.utils.session_waiter import session_waiter, SessionController
from data.plugins.astrbot_plugin_gallery.core.parse import get_image_info
from astrbot import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
import astrbot.core.message.components as Comp
from astrbot.core.platform import AstrMessageEvent
import random
from pathlib import Path

from astrbot.core.star.filter.event_message_type import EventMessageType
from data.plugins.astrbot_plugin_gallery.core.gallery import Gallery
from data.plugins.astrbot_plugin_gallery.core.gallery_manager import GalleryManager

# 图库数据存储路径
GALLERIES_DIR = Path("data/plugins_data") / "astrbot_plugin_gallery"
GALLERIES_DIR.mkdir(parents=True, exist_ok=True)

# 存储图库信息的 JSON 文件
GALLERIES_INFO_FILE = Path("data/plugins_data") / "astrbot_plugin_gallery_info.json"


@register(
    "astrbot_plugin_gallery",
    "Zhalslar",
    "本地图库管理器",
    "1.0.7",
    "https://github.com/Zhalslar/astrbot_plugin_gallery",
)
class GalleryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        # 唤醒前缀
        self.wake_prefix: list[str] = context.get_config()["wake_prefix"]

        user_config = config.get("user_config", {})
        # 用户消息长度不超过此长度时不响应
        self.user_min_msg_len: int = user_config.get("user_min_msg_len", 1)
        # 用户消息长度超过此长度时不响应
        self.user_max_msg_len: int = user_config.get("user_max_msg_len", 20)
        # 精准匹配用户消息时发送图片的概率
        self.user_exact_prob: float = user_config.get("user_exact_prob", 0.9)
        # 模糊匹配用户消息时发送图片的概率
        self.user_fuzzy_prob: float = user_config.get("user_fuzzy_prob", 0.9)

        llm_config = config.get("llm_config", {})
        # LLM消息长度不超过此长度时不响应
        self.llm_min_msg_len: int = llm_config.get("llm_min_msg_len", 1)
        # LLM消息长度超过此长度时不响应
        self.llm_max_msg_len: int = llm_config.get("llm_max_msg_len", 20)
        # 精准匹配LLM消息时发送图片的概率
        self.llm_exact_prob: float = llm_config.get("llm_exact_prob", 0.9)
        # 模糊匹配LLM消息时发送图片的概率
        self.llm_fuzzy_prob: float = llm_config.get("llm_fuzzy_prob", 0.9)

        add_default_config = config.get("add_default_config", {})
        # 下载图片时是否压缩图片
        self.default_compress_switch: bool = add_default_config.get(
            "default_compress_switch", True
        )
        # 压缩阈值(单位为像素)，图片在512像素以下时qq以表情包大小显示
        self.compress_size: int = add_default_config.get("compress_size", 512)
        # 添加图片时是否检查并跳过重复图片
        self.default_duplicate_switch: bool = add_default_config.get(
            "default_duplicate_switch", True
        )
        # 是否默认模糊匹配
        self.default_fuzzy_match: bool = add_default_config.get(
            "default_fuzzy_match", False
        )
        # 允许的图库名、图片名的最大长度
        self.label_max_length: int = add_default_config.get("label_max_length", 4)
        # 图库的默认容量
        self.max_pic_count: int = add_default_config.get("max_pic_count", 200)

        self.default_gallery_info = {
            "name": "Unknown",
            "creator_id": "Unknown",
            "creator_name": "Unknown",
            "password": 0,
            "max_capacity": self.max_pic_count,
            "compress_switch": self.default_compress_switch,
            "duplicate_switch": self.default_duplicate_switch,
            "fuzzy_match": self.default_fuzzy_match,
        }

        perm_config = config.get("perm_config", {})
        # 是否允许非管理员向任意图库添加图片
        self.allow_add: bool = perm_config.get("allow_add", False)
        # 是否允许非管理员向任意图库删除图片
        self.allow_del: bool = perm_config.get("allow_del", False)
        # 是否允许非管理员查看任意图库
        self.allow_view: bool = perm_config.get("allow_view", True)

        # 初始化总图库文件夹
        self.gm = GalleryManager(
            GALLERIES_DIR, GALLERIES_INFO_FILE, self.default_gallery_info
        )
        asyncio.create_task(self.gm.initialize())

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_match(self, event: AstrMessageEvent):
        """精准匹配/模糊匹配用户消息"""
        text = event.get_message_str()
        if self.user_min_msg_len < len(text) < self.user_max_msg_len:
            if image_path := await self._match(
                text, self.llm_exact_prob, self.llm_fuzzy_prob
            ):
                yield event.image_result(str(image_path))

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """精准匹配/模糊匹配LLM消息"""
        chain = resp.result_chain.chain
        text = (
            chain[0].text
            if len(chain) == 1 and isinstance(chain[0], Comp.Plain)
            else ""
        )
        if self.llm_min_msg_len < len(text) < self.llm_max_msg_len:
            if image_path := await self._match(
                text, self.llm_exact_prob, self.llm_fuzzy_prob
            ):
                await event.send(event.image_result(str(image_path)))

    async def _match(
        self, text: str, exact_prob: float, fuzzy_prob: float
    ) -> Path | None:
        """精准匹配/模糊匹配"""
        image_path = None
        # 精准匹配
        if text in self.gm.get_exact_match_keywords():
            if random.random() < exact_prob:
                galleris = self.gm.get_gallery_by_attribute(name=text)
                gallery = random.choice(galleris)
                image_path = gallery.get_random_image()
                logger.info(f"匹配到图片：{image_path}")

        # 模糊匹配
        for keyword in self.gm.get_fuzzy_match_keywords():
            if keyword in text:
                if random.random() < fuzzy_prob:
                    print(keyword)
                    galleris = self.gm.get_gallery_by_attribute(name=keyword)
                    gallery = random.choice(galleris)
                    image_path = gallery.get_random_image()
                    logger.info(f"匹配到图片：{image_path}")
        return image_path

    @filter.command("精准匹配词")
    async def list_accurate_keywords(self, event: AstrMessageEvent):
        """查看精准匹配词"""
        reply = f"【精准匹配词】：\n{str(self.gm.get_exact_match_keywords())}"
        yield event.plain_result(reply)

    @filter.command("模糊匹配词")
    async def list_fuzzy_keywords(self, event: AstrMessageEvent):
        """ "查看模糊匹配词"""
        reply = f"【模糊匹配词】：\n{str(self.gm.get_fuzzy_match_keywords())}"
        yield event.plain_result(reply)

    @filter.command("模糊匹配")
    async def fuzzy_match(self, event: AstrMessageEvent):
        """将图库切换到模糊匹配模式"""
        names = event.message_str.removeprefix("模糊匹配").strip().split(" ")
        for name in names:
            gallery = self._get_gallary(event, name)
            if not gallery:
                yield event.plain_result(f"未找到图库【{name}】")
                return
            result = await self.gm.set_fuzzy_match(gallery_name=name, fuzzy_match=True)
            yield event.plain_result(result)

    @filter.command("精准匹配")
    async def accurate_match(self, event: AstrMessageEvent):
        """将图库切换到精准匹配模式"""
        names = event.message_str.removeprefix("模糊匹配").strip().split(" ")
        for name in names:
            gallery = self._get_gallary(event, name)
            if not gallery:
                yield event.plain_result(f"未找到图库【{name}】")
                return
            result = await self.gm.set_fuzzy_match(gallery_name=name, fuzzy_match=False)
            yield event.plain_result(result)

    @filter.command("添加匹配词")
    async def add_ketord(
        self,
        event: AstrMessageEvent,
        gallery_name: str | None = None,
        keyword: str | None = None,
    ):
        gallery_label = self._get_label(event, gallery_name)
        gallery = self._get_gallary(event, gallery_label)
        if not gallery:
            yield event.plain_result(f"未找到图库【{gallery_label}】")
            return
        if not keyword:
            yield event.plain_result("未指定匹配词")
            return
        result = await self.gm.add_keyword(gallery_name=gallery_label, keyword=keyword)
        yield event.plain_result(result)

    @filter.command("删除匹配词")
    async def delete_keyword(
        self,
        event: AstrMessageEvent,
        gallery_name: str | None = None,
        keyword: str | None = None,
    ):
        gallery_label = self._get_label(event, gallery_name)
        gallery = self._get_gallary(event, gallery_label)
        if not gallery:
            yield event.plain_result(f"未找到图库【{gallery_label}】")
            return
        if not keyword:
            yield event.plain_result("未指定匹配词")
            return
        result = await self.gm.add_keyword(gallery_name=gallery_label, keyword=keyword)
        yield event.plain_result(result)

    @filter.command("设置容量")
    async def set_max_capacity(
        self,
        event: AstrMessageEvent,
        gallery_name: str | None = None,
        max_capacity: int = 0,
    ):
        gallery_label = self._get_label(event, gallery_name)
        gallery = self._get_gallary(event, gallery_label)
        if not gallery:
            yield event.plain_result(f"未找到图库【{gallery_label}】")
            return
        if not max_capacity:
            yield event.plain_result("未指定容量")
            return
        result = await self.gm.set_max_capacity(
            gallery_name=gallery_label, max_capacity=max_capacity
        )
        yield event.plain_result(result)

    @filter.command("开启压缩")
    async def open_compress_switch(self, event: AstrMessageEvent):
        """打开图库的压缩开关"""

        async def do_switch(name):
            return await self.gm.set_compress_switch(gallery_name=name, compress=True)

        async for r in self._toggle_gallery_switch(event, "开启压缩", do_switch):
            yield r

    @filter.command("关闭压缩")
    async def close_compress_switch(self, event: AstrMessageEvent):
        """关闭图库的压缩开关"""

        async def do_switch(name):
            return await self.gm.set_compress_switch(gallery_name=name, compress=False)

        async for r in self._toggle_gallery_switch(event, "关闭压缩", do_switch):
            yield r

    @filter.command("开启去重")
    async def open_duplicate_switch(self, event: AstrMessageEvent):
        """打开图库的去重开关"""

        async def do_switch(name):
            return await self.gm.set_duplicate_switch(gallery_name=name, duplicate=True)

        async for r in self._toggle_gallery_switch(event, "开启去重", do_switch):
            yield r

    @filter.command("关闭去重")
    async def close_duplicate_switch(self, event: AstrMessageEvent):
        """关闭图库的去重开关"""

        async def do_switch(name):
            return await self.gm.set_duplicate_switch(
                gallery_name=name, duplicate=False
            )

        async for r in self._toggle_gallery_switch(event, "关闭去重", do_switch):
            yield r

    async def _toggle_gallery_switch(
        self,
        event: AstrMessageEvent,
        prefix: str,
        switch_func: Callable[[str], Awaitable[str]],
    ):
        gallery_names = event.message_str.removeprefix(prefix).strip().split(" ")
        result = []
        for gallery_name in gallery_names:
            gallery_label = self._get_label(event, gallery_name)
            gallery = self._get_gallary(event, gallery_label)
            if not gallery:
                result.append(f"未找到图库【{gallery_name}】")
            else:
                result.append(await switch_func(gallery_name))
        yield event.plain_result("\n".join(result))

    @filter.command("存图")
    async def add_image(self, event: AstrMessageEvent):
        """
        存图 图库名 序号 (图库名不填则默认自己昵称，序号指定时会替换掉原图)
        """
        args = event.message_str.removeprefix("存图").strip().split(" ")
        gallery_name = args[0] if args and not args[0].isdigit() else None
        index = int(args[-1]) if args and args[-1].isdigit() else 0

        label = self._get_label(event)
        send_id = event.get_sender_id()

        gallery_label = self._get_label(event, gallery_name)
        gallery = self._get_gallary(event, gallery_label)

        # 图库不存在，则创建图库
        if not gallery:
            at_id = self._get_at_id(event) or "0"
            sender_name = event.get_sender_name()
            #  图库密码: 0表示公共图库不加密，否则为个人图库加密
            password = (
                "0" if (gallery_name and not gallery_name.startswith("@")) else at_id
            )
            gallery_info = {
                "name": gallery_label,
                "creator_id": send_id,
                "creator_name": sender_name,
                "password": password,
                "max_capacity": self.max_pic_count,
                "compress_switch": self.default_compress_switch,
                "duplicate_switch": self.default_duplicate_switch,
                "fuzzy_match": self.default_fuzzy_match,
            }
            gallery = await self.gm.add_gallery(gallery_info)

        #  权限验证
        if not self.allow_add or gallery.password != "0":
            if not event.is_admin() and send_id != gallery.password:
                yield event.plain_result("你无权访问此图库")
                return
        #  获取图片
        image = await self._get_image(event)

        #  图片存在，直接图片处理
        if image:
            result = gallery.add_image(
                image_bytes=image, image_label=label, index=index
            )
            yield event.plain_result(result)
        #  图片不存在，等待用户发图片
        else:
            yield event.plain_result("发一下图片")
            group_id = event.get_group_id()

            @session_waiter(timeout=30)  # type: ignore  # noqa: F821
            async def empty_mention_waiter(
                controller: SessionController, event: AstrMessageEvent
            ):
                if event.get_group_id() != group_id or event.get_sender_id() != send_id:
                    return
                image = await self._get_image(event)
                if image and gallery:
                    controller.keep(timeout=30, reset_timeout=True)
                    result = gallery.add_image(image_bytes=image, image_label=label)
                    await event.send(event.plain_result(result))
                    return

                controller.stop()

            try:
                await empty_mention_waiter(event)
            except TimeoutError as _:
                yield event.plain_result("等待超时！")
            except Exception as e:
                logger.error("批量存图发生错误：" + str(e))

            event.stop_event()

    @filter.command("删图")
    async def delete_image(self, event: AstrMessageEvent):
        """
        删图 图库名 序号/all (多个序号用空格隔开)
        """
        args = event.message_str.removeprefix("删图").strip().split(" ")
        gallery_name = args[0] if args and not args[0].isdigit() else None
        indexs = [int(arg) for arg in args if arg.isdigit()]

        gallery_label = self._get_label(event, gallery_name)
        gallery = self._get_gallary(event, gallery_label)
        if not gallery:
            yield event.plain_result(f"未找到图库【{gallery_label}】")
            return

        if not self.allow_del or gallery.password != "0":
            if not event.is_admin() and event.get_sender_id() != gallery.password:
                yield event.plain_result("你无权访问此图库")
                return

        # 删除图片
        if indexs:
            for index in indexs:
                result = "".join(gallery.delete_image_by_index(index))
                yield event.plain_result(result)

        # 删除图库
        else:
            is_deleted = await self.gm.delete_gallery(gallery_label)
            if is_deleted:
                yield event.plain_result(f"已删除图库【{gallery_label}】")
            else:
                yield event.plain_result("删除失败")

    @filter.command("查看")
    async def view_image(self, event: AstrMessageEvent):
        """
        查看 序号/图库名
        """
        args = event.message_str.removeprefix("查看").strip().split(" ")
        gallery_name = args[0] if args and not args[0].isdigit() else None
        indexs = [int(arg) for arg in args if arg.isdigit()]

        gallery_label = self._get_label(event, gallery_name)
        gallery = self._get_gallary(event, gallery_label)
        if not gallery:
            yield event.plain_result(f"未找到图库【{gallery_label}】")
            return

        if not self.allow_view or gallery.password != "0":
            if not event.is_admin() and event.get_sender_id() != gallery.password:
                yield event.plain_result("你无权访问此图库")
                return
        # 查看图片
        if indexs:
            for index in indexs:
                result = gallery.view_by_index(index)
                if isinstance(result, str):
                    yield event.plain_result(result)
                    return
                yield event.image_result(str(result))

        # 查看图库
        else:
            result = gallery.preview()
            if isinstance(result, str):
                yield event.plain_result(result)
                return
            chain = [Comp.Image.fromBytes(result)]
            yield event.chain_result(chain)  # type: ignore

    @filter.command("图库列表")
    async def view_all(self, event: AstrMessageEvent):
        """查看所有图库"""
        galleries = self.gm.galleries
        if not galleries:
            yield event.plain_result("未创建任何图库")
            return
        names = self.gm.get_all_galleries_names()
        yield event.plain_result(
            f"------共{len(galleries)}个图库------\n{'、'.join(names)}"
        )

    @filter.command("图库详情")
    async def gallery_details(
        self, event: AstrMessageEvent, gallery_name: str | None = None
    ):
        """查看图库的详细信息"""
        gallery_label = self._get_label(event, gallery_name)
        gallery = self._get_gallary(event, gallery_label)
        if not gallery:
            yield event.plain_result(f"未找到图库【{gallery_label}】")
            return
        details = (
            f"图库名称：{gallery.name}\n"
            f"图库路径：{gallery.path}\n"
            f"创建者ID：{gallery.creator_id}\n"
            f"创建者名称：{gallery.creator_name}\n"
            f"创建时间：{gallery.creation_time}\n"
            f"容量上限：{gallery.max_capacity}\n"
            f"已用容量：{len(os.listdir(gallery.path))}\n"
            f"是否压缩图片：{gallery.compress_switch}\n"
            f"是否允许重复：{gallery.duplicate_switch}\n"
            f"是否模糊匹配：{gallery.fuzzy_match}\n"
            f"图库匹配词：{gallery.keywords}"
        )
        yield event.plain_result(details)

    @filter.command("路径")
    async def find_path(self, event: AstrMessageEvent, gallery_name: str | None = None):
        """查看图库路径"""
        gallery_label = self._get_label(event, gallery_name)
        gallery = self._get_gallary(event, gallery_label)
        if not gallery:
            yield event.plain_result(f"未找到图库【{gallery_label}】")
            return
        image = await self._get_image(event)
        if not image:
            yield event.plain_result("未指定要查找的图片")
            return
        image_name = gallery.view_by_bytes(image=image)
        yield event.plain_result(f"{image_name}")

    @filter.command("解析")
    async def parse(self, event: AstrMessageEvent):
        """解析图片的信息"""
        image = await self._get_image(event)
        if not image:
            yield event.plain_result("未指定要解析的图片")
            return
        info_str = await get_image_info(image)
        if not info_str:
            yield event.plain_result("解析失败")
            return
        yield event.plain_result(info_str)

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

    def _get_label(self, event: AstrMessageEvent, label=None) -> str:
        """获取标签"""
        if not label:
            for arg in event.message_str.split(" "):
                if arg.startswith("@"):
                    label = arg.removeprefix("@")
                    break
        if not label:
            label = event.get_sender_name()
        # 过滤字符，只保留中文、数字和字母
        pattern = r"[\u4e00-\u9fa5a-zA-Z0-9]"
        filtered_label = [char for char in label if re.match(pattern, char)]
        # 截短字符串
        label_str = "".join(filtered_label)[: self.label_max_length]

        return label_str or event.get_sender_id()

    async def _get_image(self, event: AstrMessageEvent) -> bytes | None:
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

    def _get_gallary(
        self, event: AstrMessageEvent, gallery_name: str | None
    ) -> Gallery | None:
        """获取目标图库"""
        label = self._get_label(event)
        gallery_name = gallery_name or label or "Unknown"
        gallery = self.gm.get_gallery(gallery_name)
        return gallery

    def _get_at_id(self, event: AstrMessageEvent) -> str | None:
        """获取At者的ID"""
        return next(
            (
                str(seg.qq)
                for seg in event.get_messages()
                if isinstance(seg, Comp.At) and str(seg.qq) != event.get_self_id()
            ),
            None,
        )

    @filter.command("图库帮助")
    async def gallery_help(self, event: AstrMessageEvent):
        """查看图库帮助"""
        prefix = self.wake_prefix[0] if self.wake_prefix else ""
        help_text = (
            "【图库帮助】(标有s表示可输入多个,空格隔开参数,图库名皆可用@某人代替)\n\n"
            f"{prefix}精准匹配词 - 查看精准匹配词\n\n"
            f"{prefix}模糊匹配词 - 查看模糊匹配词\n\n"
            f"{prefix}模糊匹配 <图库名s> - 将指定图库切换到模糊匹配模式\n\n"
            f"{prefix}精准匹配 <图库名s> - 将指定图库切换到精准匹配模式\n\n"
            f"{prefix}添加匹配词 <图库名> <匹配词s> - 为指定图库添加匹配词\n\n"
            f"{prefix}删除匹配词 <图库名> <匹配词s> - 为指定图库删除匹配词\n\n"
            f"{prefix}设置容量 <图库名> <容量> - 设置指定图库的容量上限\n\n"
            f"{prefix}开启压缩 <图库名s> 打开指定图库的压缩开关\n\n"
            f"{prefix}关闭压缩 <图库名s> 关闭指定图库的压缩开关\n\n"
            f"{prefix}开启去重 <图库名s> 打开指定图库的去重开关\n\n"
            f"{prefix}关闭去重 <图库名s> 关闭指定图库的去重开关\n\n"
            f"{prefix}存图 <图库名> <序号> - 存图到指定图库，序号指定时会替换掉原图，图库名不填则默认自己昵称，可也@他人作为图库名\n\n"
            f"{prefix}删图 <图库名> <序号s> - 删除指定图库中的图片，序号不指定表示删除整个图库\n\n"
            f"{prefix}查看 <序号s/图库名> - 查看指定图库中的图片或图库详情，序号指定时查看单张图片\n\n"
            f"{prefix}图库列表 - 查看所有图库\n\n"
            f"{prefix}图库详情 <图库名> - 查看指定图库的详细信息\n\n"
            f"{prefix}(引用图片)/路径 <图库名> - 查看指定图片的路径，需指定在哪个图库查找\n\n"
            f"{prefix}(引用图片)/解析 - 解析图片的信息"
        )
        url = await self.text_to_image(help_text)
        yield event.image_result(url)
