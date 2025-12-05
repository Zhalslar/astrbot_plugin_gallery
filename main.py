import os

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.star.filter.event_message_type import EventMessageType
from astrbot.core.star.star_tools import StarTools
from data.plugins.astrbot_plugin_gallery.utils import HELP_TEXT, get_image

from .core import (
    GalleryDB,
    GalleryImageMerger,
    GalleryManager,
    ImageInfoExtractor,
)
from .handle.auto import GalleryAuto
from .handle.operate import GalleryOperate
from .handle.share import GalleryShare


@register("astrbot_plugin_gallery", "Zhalslar", "...", "...")
class GalleryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.conf = config
        self.plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_gallery")
        self.db_path = str(self.plugin_data_dir / "gallery_info.json")
        self.galleries_dir = os.path.abspath(config["galleries_dir"])

    async def initialize(self):
        """初始化"""
        self.db = GalleryDB(self.db_path)
        self.merger = GalleryImageMerger()
        self.extractor = ImageInfoExtractor()
        self.manager = GalleryManager(self.conf, self.db, self.galleries_dir)
        await self.manager.initialize()
        self.operator = GalleryOperate(self.conf, self.manager, self.merger)
        self.share = GalleryShare(self.conf, self.manager)
        self.auto = GalleryAuto(self.context, self.conf, self.manager)

    @filter.event_message_type(EventMessageType.ALL)
    async def auto_collect_image(self, event: AstrMessageEvent):
        """自动收集图片并打标"""
        await self.auto.collect_image(event)

    @filter.event_message_type(EventMessageType.ALL, priority=0)
    async def match_user_msg(self, event: AstrMessageEvent):
        """匹配用户消息"""
        await self.auto.match_user_msg(event)

    @filter.on_llm_response()
    async def match_llm_msg(self, event: AstrMessageEvent, resp: LLMResponse):
        """匹配LLM消息"""
        await self.auto.match_llm_msg(event, resp)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("设置标签", priority=1)
    async def add_tags(
        self,
        event: AstrMessageEvent,
    ):
        """设置图库的标签"""
        await self.operator.set_tags(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("设置容量", priority=1)
    async def set_max_capacity(self, event: AstrMessageEvent):
        """设置图库的最大容量"""
        await self.operator.set_max_capacity(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("压缩", priority=1)
    async def set_compress(self, event: AstrMessageEvent, mode: bool):
        """打开/关闭图库的压缩开关"""
        await self.operator.set_compress(event, mode)

    @filter.command("存图", priority=1)
    async def add_images(self, event: AstrMessageEvent):
        """
        存图 图库名 序号 (图库名不填则默认自己昵称，序号指定时会替换掉原图)
        """
        await self.operator.add_images(event)

    @filter.command("删图", priority=1)
    async def delete_images(self, event: AstrMessageEvent):
        """
        删图 图库名 序号/all (多个序号用空格隔开)
        """
        await self.operator.delete_images(event)

    @filter.command("看图", priority=1)
    async def view_images(self, event: AstrMessageEvent):
        """
        看图 序号/图库名
        """
        await self.operator.view_images(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("图库列表")
    async def view_all(self, event: AstrMessageEvent):
        """查看所有图库"""
        await self.operator.view_all(event)

    @filter.command("图库详情", priority=1)
    async def gallery_details(self, event: AstrMessageEvent):
        """查看图库的详细信息"""
        await self.operator.gallery_details(event)

    @filter.command("路径", priority=1)
    async def find_path(self, event: AstrMessageEvent):
        """查看图库路径"""
        await self.operator.find_path(event)

    @filter.command("上传图库", priority=1)
    async def upload_gallery(self, event: AiocqhttpMessageEvent):
        """压缩并上传图库文件夹(仅aiocqhttp)"""
        await self.share.upload_gallery(event)

    @filter.command("下载图库", priority=1)
    async def download_gallery(
        self, event: AstrMessageEvent, gallery_name: str | None = None
    ):
        """下载图库压缩包并加载(仅aiocqhttp)"""
        await self.share.download_gallery(event, gallery_name)

    @filter.command("解析")
    async def parse(self, event: AstrMessageEvent):
        """解析图片的信息"""
        image = await get_image(event)
        if not image:
            yield event.plain_result("未指定要解析的图片")
            return
        info_str = await self.extractor.get_image_info(image) # type: ignore
        if not info_str:
            yield event.plain_result("解析失败")
            return
        yield event.plain_result(info_str)

    @filter.command("图库帮助")
    async def gallery_help(self, event: AstrMessageEvent):
        """查看图库帮助"""
        url = await self.text_to_image(HELP_TEXT)
        yield event.image_result(url)
