import os

import astrbot.core.message.components as Comp
from astrbot.api import logger
from astrbot.core import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from data.plugins.astrbot_plugin_gallery.utils import (
    download_file,
    get_args,
)

from ..core import GalleryManager


class GalleryShare:
    def __init__(self, config: AstrBotConfig, manager: GalleryManager):
        self.conf = config
        self.manager = manager
        self.galleries_dir: str = os.path.abspath(config["galleries_dir"])

    async def upload_gallery(self, event: AiocqhttpMessageEvent):
        """压缩并上传图库文件夹(仅aiocqhttp)"""
        args = await get_args(event)
        for name in args["names"]:
            await event.send(event.plain_result(f"正在上传图库【{name}】..."))
            zip_path = await self.manager.compress_gallery(name)
            if not zip_path:
                await event.send(event.plain_result(f"未找到图库【{name}】"))
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

    async def download_gallery(
        self, event: AstrMessageEvent, gallery_name: str | None = None
    ):
        """下载图库压缩包并加载(仅aiocqhttp)"""
        if not gallery_name:
            await event.send(event.plain_result("必须输入一个新图库名"))
            return
        if gallery_name in self.manager.get_all_galleries_names():
            await event.send(event.plain_result(f"图库名【{gallery_name}】已被占用"))
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
            await event.send(event.plain_result("请引用一个zip文件"))
            return
        await event.send(event.plain_result("正在下载..."))
        logger.info(f"正在从URL下载文件：{url}")
        file: bytes | None = await download_file(url)
        if not file:
            await event.send(event.plain_result("文件下载失败"))
            return
        save_path = os.path.join(self.galleries_dir, f"{gallery_name}.zip")
        try:
            with open(save_path, "wb") as f:
                f.write(file)
            await self.manager._load_from_zips()
            await event.send(event.plain_result(f"✅成功下载并加载图库【{gallery_name}】"))
        except Exception as e:
            await event.send(event.plain_result(f"保存文件时出错: {e}"))
            return

