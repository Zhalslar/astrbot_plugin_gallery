
import os
import random
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
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.event_message_type import EventMessageType
from data.plugins.astrbot_plugin_gallery.core.gallery import Gallery
from data.plugins.astrbot_plugin_gallery.core.gallery_manager import GalleryManager
from data.plugins.astrbot_plugin_gallery.utils import download_file, get_args, get_image

# 存储图库信息的 JSON 文件
GALLERIES_INFO_FILE = os.path.join("data", "plugins_data", "astrbot_plugin_gallery_info.json")


@register(
    "astrbot_plugin_gallery",
    "Zhalslar",
    "本地图库管理器",
    "2.0.2",
    "https://github.com/Zhalslar/astrbot_plugin_gallery",
)
class GalleryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

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
        self.default_compress: bool = add_default_config.get(
            "default_compress", True
        )
        # 压缩阈值(单位为像素)，图片在512像素以下时qq以表情包大小显示
        self.compress_size: int = add_default_config.get("compress_size", 512)
        # 添加图片时是否检查并跳过重复图片
        self.default_duplicate: bool = add_default_config.get(
            "default_duplicate", True
        )
        # 是否默认模糊匹配
        self.default_fuzzy: bool = add_default_config.get(
            "default_fuzzy", False
        )
        # 图库的默认容量
        self.default_capacity: int = add_default_config.get("default_capacity", 200)

        perm_config = config.get("perm_config", {})
        # 是否允许非管理员向任意图库添加图片
        self.allow_add: bool = perm_config.get("allow_add", False)
        # 是否允许非管理员向任意图库删除图片
        self.allow_del: bool = perm_config.get("allow_del", False)
        # 是否允许非管理员查看任意图库
        self.allow_view: bool = perm_config.get("allow_view", True)

        auto_collect_config = config.get("auto_collect_config", {})
        # 是否启用自动收集功能
        self.enable_collect: bool = auto_collect_config.get("enable_collect", False)
        # 自动收集的群聊白名单, 留空表示启用所有群聊
        self.white_list: list[str] = auto_collect_config.get("white_list", [])
        # 收集的图片大小限制(MB)
        self.collect_compressed_img: int = auto_collect_config.get(
            "collect_compressed_img", False
        )
        # 唤醒前缀
        self.wake_prefix: list[str] = context.get_config()["wake_prefix"]

        # 总图库文件夹目录
        self.galleries_dirs = [
            os.path.abspath(dir_path) for dir_path in
            config.get("galleries_dirs", ["temp_galleries"])
        ]

        self.default_gallery_info = {
            "name": "local",
            "path": os.path.join(os.path.abspath(self.galleries_dirs[0]), "local"),
            "creator_id": "127001",
            "creator_name": "local",
            "capacity": self.default_capacity,
            "compress": self.default_compress,
            "duplicate": self.default_duplicate,
            "fuzzy": self.default_fuzzy,
        }

    async def initialize(self):
        """启动时初始化图库"""
        self.gm = GalleryManager(
            self.galleries_dirs, GALLERIES_INFO_FILE, self.default_gallery_info
        )
        await self.gm.initialize()

    async def _creat_gallery(self, event: AstrMessageEvent, name: str) -> Gallery:
        """
        创建图库 图库名
        """
        gallery_info = self.default_gallery_info.copy()
        gallery_info["path"] = os.path.join(self.galleries_dirs[0], name)
        gallery_info["creator_id"] = event.get_sender_id()
        gallery_info["creator_name"] = event.get_sender_name()
        gallery = await self.gm.load_gallery(gallery_info)
        return gallery

    @filter.event_message_type(EventMessageType.ALL)
    async def auto_collect_image(self, event: AstrMessageEvent):
        """自动收集图片"""
        # 开关
        if not self.enable_collect:
            return
        # 群聊白名单
        if self.white_list and event.get_group_id() not in self.white_list:
            return
        # 响应含有图片的消息
        chain = event.get_messages()
        if len(chain) == 1 and isinstance(chain[0], Comp.Image):
            args = await get_args(event, "")
            name = args["names"][0]
            label = args["labels"][0]
            # 获取对应用户的图库
            gallery = self.gm.get_gallery(name)
            # 图库不存在则创建
            if not gallery:
                gallery = await self._creat_gallery(event, name=name)

            if image := await get_image(event, reply=False):
                # 如果配置为“不收集需要压缩的图片” 且 当前图片需要压缩
                if not self.collect_compressed_img and gallery.need_compress(image):
                    # 如果图库当前没有图片（即是空的），就删除这个图库
                    if not len(os.listdir(gallery.path)):
                         await self.gm.delete_gallery(name)
                    return
                # 收集图片
                result = gallery.add_image(image=image, label=label)
                if result.text:
                    logger.info(f"自动收集图片：{result.text}")
    @filter.event_message_type(EventMessageType.ALL, priority=0)
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
                await event.send(event.image_result(image_path))

    async def _match(
        self, text: str, exact_prob: float, fuzzy_prob: float
    ) -> str | None:
        """精准匹配/模糊匹配"""
        # 精准匹配
        if random.random() < exact_prob and text in self.gm.exact_keywords:
            galleris = self.gm.get_gallery_by_attribute(name=text)
            gallery = random.choice(galleris)
            result = gallery.get_random_image()
            if result.image_path:
                logger.info(f"匹配到图片：{result.image_path}")
                return result.image_path

        # 模糊匹配
        if random.random() < fuzzy_prob:
            for keyword in self.gm.fuzzy_keywords:
                if keyword in text:
                    galleris = self.gm.get_gallery_by_keyword(keyword)
                    gallery = random.choice(galleris)
                    result = gallery.get_random_image()
                    if result.image_path:
                        logger.info(f"匹配到图片：{result.image_path}")
                        return result.image_path

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("精准匹配词", priority=1)
    async def list_accurate_keywords(self, event: AstrMessageEvent):
        """查看精准匹配词"""
        reply = f"【精准匹配词】：\n{str(self.gm.exact_keywords)}"
        yield event.plain_result(reply)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("模糊匹配词", priority=1)
    async def list_fuzzy_keywords(self, event: AstrMessageEvent):
        """ "查看模糊匹配词"""
        reply = f"【模糊匹配词】：\n{str(self.gm.fuzzy_keywords)}"
        yield event.plain_result(reply)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("模糊匹配", priority=1)
    async def fuzzy_match(self, event: AstrMessageEvent):
        """将图库切换到模糊匹配模式"""
        args = await get_args(event, "模糊匹配")
        for name in args["names"]:
            gallery = self.gm.get_gallery(name)
            if not gallery:
                yield event.plain_result(f"未找到图库【{name}】")
                return
            result = await self.gm.set_fuzzy(name, fuzzy=True)
            yield event.plain_result(result)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("精准匹配", priority=1)
    async def accurate_match(self, event: AstrMessageEvent):
        """将图库切换到精准匹配模式"""
        args = await get_args(event, "精准匹配")
        for name in args["names"]:
            gallery = self.gm.get_gallery(name)
            if not gallery:
                yield event.plain_result(f"未找到图库【{name}】")
                return
            result = await self.gm.set_fuzzy(name, fuzzy=False)
            yield event.plain_result(result)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("添加匹配词", priority=1)
    async def add_keyword(
        self,
        event: AstrMessageEvent,
    ):
        """添加匹配词到指定图库"""
        args = await get_args(event, "添加匹配词")
        name = args["names"][0]
        keywords = args["texts"]
        gallery = self.gm.get_gallery(name)
        if not gallery:
            yield event.plain_result(f"未找到图库【{name}】")
            return
        if not keywords:
            yield event.plain_result("未指定匹配词")
            return
        result = []
        for keyword in set(keywords) - set(gallery.keywords):
            result.append(await self.gm.add_keyword(name, keyword=keyword))
        yield event.plain_result("\n".join(result))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("删除匹配词", priority=1)
    async def delete_keyword(self, event: AstrMessageEvent):
        """删除指定图库的匹配词"""
        args = await get_args(event, "删除匹配词")
        name = args["names"][0]
        keywords = args["texts"]

        gallery = self.gm.get_gallery(name)
        if not gallery:
            yield event.plain_result(f"未找到图库【{name}】")
            return

        if not keywords:
            yield event.plain_result("未指定匹配词")
            return

        result = []
        for keyword in set(keywords) - set(gallery.keywords):
            result.append(
                await self.gm.delete_keyword(name, keyword=keyword)
            )
        yield event.plain_result("\n".join(result))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("设置容量", priority=1)
    async def set_max_capacity(self, event: AstrMessageEvent):
        """设置指定图库的最大容量"""
        args = await get_args(event, "设置容量")
        name = args["names"][0]
        capacity = args["numbers"][0]
        result = await self.gm.set_capacity(name, capacity=capacity)
        yield event.plain_result(result)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("打开压缩", priority=1)
    async def open_compress(self, event: AstrMessageEvent):
        """打开图库的压缩开关"""

        async def do_switch(name):
            return await self.gm.set_compress(name, compress=True)

        async for r in self._toggle_gallery_switch(event, "打开压缩", do_switch):
            yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("关闭压缩", priority=1)
    async def close_compress(self, event: AstrMessageEvent):
        """关闭图库的压缩开关"""

        async def do_switch(name):
            return await self.gm.set_compress(name, compress=False)

        async for r in self._toggle_gallery_switch(event, "关闭压缩", do_switch):
            yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("打开去重", priority=1)
    async def open_duplicate(self, event: AstrMessageEvent):
        """打开图库的去重开关"""

        async def do_switch(name):
            return await self.gm.set_duplicate(name, duplicate=True)

        async for r in self._toggle_gallery_switch(event, "打开去重", do_switch):
            yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("关闭去重", priority=1)
    async def close_duplicate(self, event: AstrMessageEvent):
        """关闭图库的去重开关"""

        async def do_switch(name):
            return await self.gm.set_duplicate(name, duplicate=False)

        async for r in self._toggle_gallery_switch(event, "关闭去重", do_switch):
            yield r

    @filter.command("去重", priority=1)
    async def remove_duplicates(self, event: AstrMessageEvent):
        """去除指定图库的重复图片"""
        args = await get_args(event, "去重")
        names = args["names"]
        reply = []
        for name in names:
            if gallery := self.gm.get_gallery(name):
                gallery.remove_duplicates()
                reply.append(f"图库【{name}】已去重")
        yield event.plain_result("\n".join(reply))

    async def _toggle_gallery_switch(
        self,
        event: AstrMessageEvent,
        prefix: str,
        switch_func: Callable[[str], Awaitable[str]],
    ):
        args = await get_args(event, prefix)
        result = []
        for name in args["names"]:
            args = await get_args(event, "设置容量")

            gallery = self.gm.get_gallery(name)
            if not gallery:
                result.append(f"未找到图库【{name}】")
            else:
                result.append(await switch_func(name))
        yield event.plain_result("\n".join(result))

    def verify_perm(self, event: AstrMessageEvent, gallery: Gallery, allow_noadmin:bool) -> bool:
        """验证权限"""
        if not allow_noadmin or (gallery.name.isdigit() and int(gallery.name) > 10000):
            if not event.is_admin() and event.get_sender_id() != gallery.name:
                return False
        return True

    @filter.command("存图", priority=1)
    async def add_image(self, event: AstrMessageEvent):
        """
        存图 图库名 序号 (图库名不填则默认自己昵称，序号指定时会替换掉原图)
        """
        args = await get_args(event, "存图")
        print(args)
        name = args["names"][0]
        index = args["numbers"][0]
        label = args["labels"][0]

        send_id = event.get_sender_id()
        gallery = self.gm.get_gallery(name)

        if not gallery:
            gallery = await self._creat_gallery(event, name=name)

        #  权限验证
        if self.verify_perm(event, gallery, self.allow_add) is False:
            yield event.plain_result(f"你无权操作图库【{name}】")
            return

        #  获取图片
        image = await get_image(event)

        #  图片存在，直接图片处理
        if image:
            result = gallery.add_image(image=image, label=label, index=index)
            if result.text:
                yield event.plain_result(result.text)
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
                image = await get_image(event)
                if image and gallery:
                    controller.keep(timeout=30, reset_timeout=True)
                    result = gallery.add_image(image=image, label=label)
                    if result.text:
                        await event.send(event.plain_result(result.text))
                    return

                controller.stop()

            try:
                await empty_mention_waiter(event)
            except TimeoutError as _:
                yield event.plain_result("存图结束")
            except Exception as e:
                logger.error("批量存图发生错误：" + str(e))

            event.stop_event()

    @filter.command("删图", priority=1)
    async def delete_image(self, event: AstrMessageEvent):
        """
        删图 图库名 序号/all (多个序号用空格隔开)
        """
        args = await get_args(event, "删图")
        name = args["names"][0]
        indexs = args["numbers"]

        gallery = self.gm.get_gallery(name)
        if not gallery:
            yield event.plain_result(f"未找到图库【{name}】")
            return

        #  权限验证
        if self.verify_perm(event, gallery, self.allow_del) is False:
            yield event.plain_result(f"你无权操作图库【{name}】")
            return

        # 删除图片
        if indexs != [0]:
            reply = []
            for index in indexs:
                result = gallery.delete_image_by_index(index)
                if result.text:
                    reply.append(result.text)
            yield event.plain_result("\n".join(reply))
        # 删除图库
        else:
            is_deleted = await self.gm.delete_gallery(name)
            reply = f"已删除图库【{name}】" if is_deleted else "删除图库【{name}】失败"
            yield event.plain_result(reply)

    @filter.command("查看", priority=1)
    async def view_image(self, event: AstrMessageEvent):
        """
        查看 序号/图库名
        """
        args = await get_args(event, "查看")
        name = args["names"][0]
        indexs = args["numbers"]

        gallery = self.gm.get_gallery(name)
        if not gallery:
            yield event.plain_result(f"未找到图库【{name}】")
            return

        #  权限验证
        if self.verify_perm(event, gallery, self.allow_view) is False:
            yield event.plain_result(f"你无权查看图库【{name}】")
            return

        # 查看图片
        if indexs != [0]:
            for index in indexs:
                result = gallery.view_by_index(index)
                if result.text:
                    yield event.plain_result(result.text)
                    return
                if result.image_path:
                    yield event.image_result(result.image_path)

        # 查看图库
        else:
            result = gallery.preview()
            if isinstance(result, str):
                yield event.plain_result(result)
                return
            if result.image_bytes:
                chain = [Comp.Image.fromBytes(result.image_bytes)]
            yield event.chain_result(chain)  # type: ignore

    @filter.permission_type(filter.PermissionType.ADMIN)
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

    @filter.command("图库详情", priority=1)
    async def gallery_details(self, event: AstrMessageEvent):
        """查看图库的详细信息"""
        args = await get_args(event, "图库详情")
        for name in args["names"]:
            gallery = self.gm.get_gallery(name)
            if not gallery:
                yield event.plain_result(f"未找到图库【{name}】")
                return
            details = (
                f"图库名称：{gallery.name}\n"
                f"图库路径：{gallery.path}\n"
                f"创建者ID：{gallery.creator_id}\n"
                f"创建之人：{gallery.creator_name}\n"
                f"创建时间：{gallery.creation_time}\n"
                f"容量上限：{gallery.capacity}\n"
                f"已用容量：{len(os.listdir(gallery.path))}\n"
                f"压缩图片：{gallery.compress}\n"
                f"图片去重：{gallery.duplicate}\n"
                f"模糊匹配：{gallery.fuzzy}\n"
                f"匹配词： {gallery.keywords}"
            )
            yield event.plain_result(details)

    @filter.command("路径", priority=1)
    async def find_path(self, event: AstrMessageEvent):
        """查看图库路径"""
        args = await get_args(event, "路径")
        for name in args["names"]:
            gallery = self.gm.get_gallery(name)
            if not gallery:
                yield event.plain_result(f"未找到图库【{name}】")
                return
            image = await get_image(event)
            if not image:
                yield event.plain_result(f"图库【{name}】中无此图")
                return
            result = gallery.view_by_bytes(image=image)
            if result.text:
                yield event.plain_result(f"{result.text}")

    @filter.command("上传图库", priority=1)
    async def upload_gallery(self, event: AiocqhttpMessageEvent):
        """压缩并上传图库文件夹(仅aiocqhttp)"""
        args = await get_args(event, "上传图库")
        for name in args["names"]:
            yield event.plain_result(f"正在上传图库【{name}】...")
            zip_path = await self.gm.compress_gallery(name)
            if not zip_path:
                yield event.plain_result(f"未找到图库【{name}】")
                return
            client = event.bot
            group_id = event.get_group_id()
            if group_id:
                await client.upload_group_file(
                    group_id=int(group_id),
                    file=zip_path,
                    name=os.path.basename(zip_path),
                )
            else:
                await client.upload_private_file(
                    user_id=int(event.get_sender_id()),
                    file=str(zip_path),
                    name=os.path.basename(zip_path),
                )

    @filter.command("下载图库", priority=1)
    async def download_gallery(self, event: AstrMessageEvent, gallery_name: str | None =None):
        """下载图库压缩包并加载(仅aiocqhttp)"""
        if not gallery_name:
            yield event.plain_result("必须输入一个新图库名")
            return
        if gallery_name in self.gm.get_all_galleries_names():
            yield event.plain_result(f"图库名【{gallery_name}】已被占用")
            return
        chain = event.message_obj.message
        logger.debug(chain)
        reply_chain = (
            chain[0].chain if chain and isinstance(chain[0], Comp.Reply) else None
        )
        url = (
            reply_chain[0].url
            if reply_chain and isinstance(reply_chain[0], Comp.File)
            else None
        )
        if not url:
            yield event.plain_result("请引用一个zip文件")
            return
        yield event.plain_result("正在下载...")
        logger.info(f"正在从URL下载文件：{url}")
        file: bytes|None = await download_file(url)
        if not file:
            yield event.plain_result("文件下载失败")
            return
        save_path = os.path.join(self.galleries_dirs[0], f"{gallery_name}.zip")
        try:
            with open(save_path, "wb") as f:
                f.write(file)
            await self.gm.load_zips()
            yield event.plain_result(
                f"✅成功下载并加载图库【{gallery_name}】"
            )
        except Exception as e:
            yield event.plain_result(f"保存文件时出错: {e}")
            return

    @filter.command("解析")
    async def parse(self, event: AstrMessageEvent):
        """解析图片的信息"""
        image = await get_image(event)
        if not image:
            yield event.plain_result("未指定要解析的图片")
            return
        info_str = await get_image_info(image)
        if not info_str:
            yield event.plain_result("解析失败")
            return
        yield event.plain_result(info_str)

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
            f"{prefix}去重 <图库名s> 去除图库里重复的图片\n\n"
            f"{prefix}存图 <图库名> <序号> - 存图到指定图库，序号指定时会替换掉原图，图库名不填则默认自己昵称，可也@他人作为图库名\n\n"
            f"{prefix}删图 <图库名> <序号s> - 删除指定图库中的图片，序号不指定表示删除整个图库\n\n"
            f"{prefix}查看 <序号s/图库名> - 查看指定图库中的图片或图库详情，序号指定时查看单张图片\n\n"
            f"{prefix}图库列表 - 查看所有图库\n\n"
            f"{prefix}图库详情 <图库名s> - 查看指定图库的详细信息\n\n"
            f"{prefix}(引用图片)/路径 <图库名s> - 查看指定图片的路径，需指定在哪个图库查找\n\n"
            f"{prefix}(引用图片)/解析 - 解析图片的信息"
            f"{prefix}上传图库 <图库名s> - 将图库打包成ZIP上传"
            f"{prefix}(引用ZIP)下载图库 <图库名> - 下载ZIP重命名后加载为图库"
        )
        url = await self.text_to_image(help_text)
        yield event.image_result(url)
