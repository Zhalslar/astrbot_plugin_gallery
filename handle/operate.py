from astrbot.api import logger
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Image
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.utils.session_waiter import SessionController, session_waiter
from data.plugins.astrbot_plugin_gallery.utils import (
    get_args,
    get_image,
)

from ..core import Gallery, GalleryImageMerger, GalleryManager


class GalleryOperate:
    def __init__(
        self, config: AstrBotConfig, manager: GalleryManager, merger: GalleryImageMerger
    ):
        self.manager = manager
        self.conf = config
        self.merger = merger

    def verify_perm(
        self, event: AstrMessageEvent, gallery: Gallery, allow_noadmin: bool
    ) -> bool:
        """验证权限"""
        if not allow_noadmin or (gallery.name.isdigit() and int(gallery.name) > 10000):
            if not event.is_admin() and event.get_sender_id() != gallery.name:
                return False
        return True

    async def set_tags(self, event: AstrMessageEvent):
        """设置图库的标签"""
        args = await get_args(event)
        name = args["names"][0]
        tags = args["texts"]
        gallery = self.manager.get_gallery(name)
        if not gallery:
            await event.send(event.plain_result(f"未找到图库【{name}】"))
            return
        if not tags:
            await event.send(event.plain_result("未指定标签"))
            return
        result = await self.manager.set_tags(name, tags)
        await event.send(event.plain_result(result))

    async def set_max_capacity(self, event: AstrMessageEvent):
        """设置指定图库的最大容量"""
        args = await get_args(event)
        name = args["names"][0]
        capacity = args["numbers"][0]
        result = await self.manager.set_capacity(name, capacity=capacity)
        await event.send(event.plain_result(result))

    async def set_compress(self, event: AstrMessageEvent, mode: bool):
        """打开/关闭图库的压缩开关"""
        args = await get_args(event)
        result = []
        for name in args["names"]:
            gallery = self.manager.get_gallery(name)
            if not gallery:
                result.append(f"未找到图库【{name}】")
            else:
                msg = await self.manager.set_compress(name, compress=mode)
                result.append(msg)
        await event.send(event.plain_result("\n".join(result)))

    async def add_images(self, event: AstrMessageEvent):
        """
        存图 图库名 序号 (图库名不填则默认自己昵称，序号指定时会替换掉原图)
        """
        args = await get_args(event)
        name = args["names"][0]
        index = args["numbers"][0]
        author = args["labels"][0]

        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()

        gallery = self.manager.get_gallery(name) or await self.manager.create_gallery(
            name, sender_id, sender_name
        )

        #  权限验证
        perm = self.conf["perm_config"]["allow_add"]
        if self.verify_perm(event, gallery, perm) is False:
            await event.send(event.plain_result(f"你无权操作图库【{name}】"))
            return

        #  获取图片
        image = await get_image(event)

        #  图片存在，直接图片处理
        if image:
            succ, result = gallery.add_image(image=image, author=author, index=index)  # type: ignore
            if succ:
                await event.send(event.plain_result(result))
        #  图片不存在，等待用户发图片
        else:
            await event.send(event.plain_result("发一下图片"))
            group_id = event.get_group_id()

            @session_waiter(timeout=30)  # type: ignore  # noqa: F821
            async def empty_mention_waiter(
                controller: SessionController, event: AstrMessageEvent
            ):
                if (
                    event.get_group_id() != group_id
                    or event.get_sender_id() != sender_id
                ):
                    return
                image = await get_image(event)
                if image and gallery:
                    controller.keep(timeout=30, reset_timeout=True)
                    succ, result = gallery.add_image(image=image, author=author)  # type: ignore
                    if succ:
                        await event.send(event.plain_result(result))
                    return

                controller.stop()

            try:
                await empty_mention_waiter(event)
            except TimeoutError as _:
                await event.send(event.plain_result("存图结束"))
            except Exception as e:
                logger.error("批量存图发生错误：" + str(e))

            event.stop_event()

    async def delete_images(self, event: AstrMessageEvent):
        """
        删图 图库名 序号/all (多个序号用空格隔开)
        """
        args = await get_args(event)
        name = args["names"][0]
        indexs = args["numbers"]

        gallery = self.manager.get_gallery(name)
        if not gallery:
            await event.send(event.plain_result(f"未找到图库【{name}】"))
            return

        #  权限验证
        perm = self.conf["perm_config"]["allow_del"]
        if self.verify_perm(event, gallery, perm) is False:
            await event.send(event.plain_result(f"你无权操作图库【{name}】"))
            return

        # 删除图片
        if indexs != [0]:
            reply = []
            for index in indexs:
                succ, result = gallery.delete_image_by_index(index)
                if succ:
                    reply.append(result)
            await event.send(event.plain_result("\n".join(reply)))
        # 删除图库
        else:
            is_deleted = await self.manager.delete_gallery(name)
            reply = f"已删除图库【{name}】" if is_deleted else "删除图库【{name}】失败"
            await event.send(event.plain_result(reply))

    async def view_images(self, event: AstrMessageEvent):
        """
        看图 序号/图库名
        """
        args = await get_args(event)
        name = args["names"][0]
        indexs = args["numbers"]

        gallery = self.manager.get_gallery(name)
        if not gallery:
            await event.send(event.plain_result(f"未找到图库【{name}】"))
            return

        #  权限验证
        perm = self.conf["perm_config"]["allow_view"]
        if self.verify_perm(event, gallery, perm) is False:
            await event.send(event.plain_result(f"你无权查看图库【{name}】"))
            return

        # 查看图片
        if indexs != [0]:
            for index in indexs:
                succ, result = gallery.view_by_index(index)
                if succ:
                    await event.send(event.image_result(result))  # type: ignore
                else:
                    await event.send(event.plain_result(result))  # type: ignore

        # 查看图库
        else:
            merged = self.merger.create_merged(gallery.path)
            if merged:
                await event.send(event.chain_result([Image.fromBytes(merged)]))
            else:
                await event.send(event.plain_result(f"图库【{name}】为空"))

    async def view_all(self, event: AstrMessageEvent):
        """查看所有图库"""
        galleries = self.manager.galleries
        if not galleries:
            await event.send(event.plain_result("未创建任何图库"))
            return
        names = self.manager.get_all_galleries_names()
        await event.send(
            event.plain_result(
                f"------共{len(galleries)}个图库------\n{'、'.join(names)}"
            )
        )

    async def gallery_details(self, event: AstrMessageEvent):
        """查看图库的详细信息"""
        args = await get_args(event)
        for name in args["names"]:
            gallery = self.manager.get_gallery(name)
            if not gallery:
                await event.send(event.plain_result(f"未找到图库【{name}】"))
                return
            await event.send(event.plain_result(gallery.to_str()))

    async def find_path(self, event: AstrMessageEvent):
        """查看图库路径"""
        args = await get_args(event)
        for name in args["names"]:
            gallery = self.manager.get_gallery(name)
            if not gallery:
                await event.send(event.plain_result(f"未找到图库【{name}】"))
                return
            image = await get_image(event)
            if not image:
                await event.send(event.plain_result(f"图库【{name}】中无此图"))
                return
            succ, result = gallery.view_by_bytes(image=image)  # type: ignore
            await event.send(event.plain_result(str(result)))
