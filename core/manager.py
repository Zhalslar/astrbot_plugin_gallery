import asyncio
import os
from pathlib import Path

from astrbot import logger
from astrbot.core.config.astrbot_config import AstrBotConfig

from .db import GalleryDB
from .gallery import Gallery
from .zip_utils import ZipUtils


class GalleryManager:
    """
    图库管理器类，负责管理所有图库的创建、删除和操作；
    内部维护一个图库列表
    """

    def __init__(self, config: AstrBotConfig, db: GalleryDB, galleries_dir: Path):
        """
        初始化图库管理器
        """
        self.galleries_dir = galleries_dir
        self.conf = config
        self.compress = self.conf["add_default"]["compress"]
        self.capacity = self.conf["add_default"]["capacity"]
        self.galleries: dict[str, Gallery] = {}
        self.db = db

    # ----------------- 初始化，加载图库实例 -----------------

    async def initialize(self):
        """
        初始化图库管理器
        """
        logger.info("图库管理器初始化中...")
        logger.debug(f"图库总目录：{self.galleries_dir}")

        await self.db.initialize()
        await self._load_from_db()
        logger.debug("从数据库中加载实例完成")

        await self._load_new_folder()
        logger.debug("从新的文件夹中加载实例完成")

        await self._load_from_zips()
        logger.debug("从zip文件中加载实例完成")

        logger.info("图库管理器插件初始化完成")

    async def _load_from_db(self):
        """从 DB 加载图库定义"""
        data = await self.db.load_valid()
        tasks = [self.load_gallery(info) for info in data]
        await asyncio.gather(*tasks)

    async def _load_new_folder(self):
        """
        从新的文件夹中加载图库
        """
        for item in self.galleries_dir.iterdir():
            if item.is_dir() and item.name not in self.galleries:
                info = {
                    "path": str(item.resolve()),
                    "creator_id": "new",
                    "creator_name": "new",
                    "capacity": self.capacity,
                    "compress": self.compress,
                }
                await self.load_gallery(info)

    async def _load_from_zips(self):
        """从 ZIP 文件中加载图库"""
        for folder_path in ZipUtils.extract_all_zips(str(self.galleries_dir)):
            info = {
                "path": folder_path,
                "creator_id": "zip",
                "creator_name": "zip",
                "capacity": self.capacity,
                "compress": self.compress,
            }
            await self.load_gallery(info)

    async def _save_to_db(self):
        """统一保存入口"""
        data = [g.to_dict() for g in self.galleries.values()]
        await self.db.save_all(data)

    # ----------------- 业务接口 -----------------

    async def compress_gallery(self, name: str) -> str | None:
        """
        将指定图库压缩为ZIP文件
        :param name: 图库名称
        """
        folder_path = self.galleries_dir / name
        if folder_path.is_dir():
            zip_path = self.galleries_dir / f"{name}.zip"
            logger.info(f"正在将图库【{name}】压缩为ZIP文件")
            if not ZipUtils.zip_folder(str(folder_path), str(zip_path)):
                logger.error(f"压缩文件夹失败: {folder_path}")
                return None
            logger.info(f"图库【{name}】已成功压缩为ZIP文件：{zip_path}")
            return str(zip_path)
        return None

    async def create_gallery(
        self, name: str, creator_id: str = "default", creator_name="default"
    ) -> Gallery:
        """
        创建图库
        """
        gallery = Gallery(
            path=os.path.join(self.galleries_dir, name),
            creator_id=creator_id,
            creator_name=creator_name,
            capacity=self.capacity,
            compress=self.compress,
        )
        self.galleries[gallery.name] = gallery
        await self._save_to_db()
        return gallery

    async def load_gallery(self, gallery_info: dict) -> Gallery:
        """
        加载图库为实例
        :param gallery_info: 图库信息字典
        """
        gallery = Gallery.from_dict(gallery_info)
        self.galleries[gallery.name] = gallery
        await self._save_to_db()
        return gallery

    async def save_gallery(self, gallery: Gallery):
        """
        接收一个 Gallery 实例并保存到管理器与数据库中
        """
        self.galleries[gallery.name] = gallery
        await self._save_to_db()

        return f"图库【{gallery.name}】已保存"

    async def delete_gallery(self, name: str) -> bool:
        """
        根据图库名删除图库
        :param gallery_name: 图库名
        """
        if name in self.galleries:
            gallery = self.galleries[name]
            gallery.delete()  # 删除图库文件夹
            del self.galleries[name]  # 从字典中删除图库实例
            await self._save_to_db()
            return True
        else:
            logger.error(f"图库不存在：{name}")
            return False

    def get_gallery(self, name: str) -> Gallery | None:
        """根据图库名获取图库实例"""
        return self.galleries.get(name)

    def get_all_gallery(self):
        """获取所有图库实例"""
        return list(self.galleries.values())

    def get_gallery_by_attribute(self, **filters) -> list[Gallery]:
        """
        根据给定的属性和值获取图库实例列表
        :param filters: 以关键字参数的形式提供过滤条件
        :return: 满足条件的图库实例列表
        """
        return [
            gallery
            for gallery in self.galleries.values()
            if all(getattr(gallery, key) == value for key, value in filters.items())
        ]

    def get_gallery_by_tag(self, tag) -> list[Gallery]:
        """
        根据给定的匹配词获取图库实例列表
        :param tag: 标签
        :return: 满足条件的图库实例列表
        """
        return [gallery for gallery in self.galleries.values() if tag in gallery.tags]

    def get_all_galleries_names(self) -> list[str]:
        """
        获取所有图库的名称，组合成列表
        :return: 图库名称列表
        """
        return list(self.galleries.keys())

    async def set_capacity(self, name: str, capacity: int):
        """设置图库容量上限"""
        if gallery := self.get_gallery(name):
            if capacity > 0:
                gallery.capacity = capacity
                await self._save_to_db()
                return f"图库【{name}】容量上限已设置为：{capacity}"
            else:
                return f"图库容量上限错误：{capacity}，必须大于0"
        return f"图库【{name}】不存在"

    async def set_compress(self, name: str, compress: bool):
        """设置图库新增图片时是否压缩"""
        if gallery := self.get_gallery(name):
            gallery.compress = compress
            await self._save_to_db()
            return f"图库【{gallery.name}】压缩开关: {gallery.compress}"
        return f"图库【{name}】不存在"

    async def set_tags(self, name: str, tags: list[str]) -> str:
        """设置图库标签"""
        if gallery := self.get_gallery(name):
            gallery.tags = tags
            await self._save_to_db()
            return f"图库【{gallery.name}】标签已设为：{tags}"
        return f"图库【{name}】不存在"
