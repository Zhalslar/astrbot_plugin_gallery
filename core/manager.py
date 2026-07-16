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
        add_default = self.conf["add_default"]
        self.compress = add_default["compress"]
        self.compress_size = add_default.get("compress_size", 512)
        self.capacity = add_default["capacity"]
        # 新增字段的默认值
        self.match_mode = add_default.get("match_mode", "fuzzy")
        self.dedup_enabled = add_default.get("dedup_enabled", True)
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

        # 为所有图库构建 dhash 缓存（用于近似判重）
        await self._build_dhash_cache_for_all()

        logger.info("图库管理器插件初始化完成")

    async def _build_dhash_cache_for_all(self):
        """为所有已加载的图库构建 dhash 缓存"""
        logger.info("正在构建 dhash 缓存...")
        tasks = [gallery._build_dhash_cache() for gallery in self.galleries.values()]
        await asyncio.gather(*tasks)
        logger.info("dhash 缓存构建完成")

    async def _load_from_db(self):
        """从 DB 加载图库定义"""
        data = await self.db.load_valid()
        tasks = [self.load_gallery(info) for info in data]
        await asyncio.gather(*tasks)

    async def _load_new_folder(self):
        """
        从新的文件夹中加载图库
        """
        loaded_new = False
        for item in self.galleries_dir.iterdir():
            if item.is_dir() and item.name not in self.galleries:
                info = {
                    "path": str(item.resolve()),
                    "creator_id": "new",
                    "creator_name": "new",
                    "capacity": self.capacity,
                    "compress": self.compress,
                    "compress_size": self.compress_size,
                    "match_mode": self.match_mode,
                    "dedup_enabled": self.dedup_enabled,
                }
                await self.load_gallery(info)
                loaded_new = True
        # 只有加载了新的图库时才保存到数据库
        if loaded_new:
            await self._save_to_db()

    async def _load_from_zips(self):
        """从 ZIP 文件中加载图库"""
        loaded_from_zips = False
        for folder_path in ZipUtils.extract_all_zips(str(self.galleries_dir)):
            info = {
                "path": folder_path,
                "creator_id": "zip",
                "creator_name": "zip",
                "capacity": self.capacity,
                "compress": self.compress,
                "compress_size": self.compress_size,
                "match_mode": self.match_mode,
                "dedup_enabled": self.dedup_enabled,
            }
            await self.load_gallery(info)
            loaded_from_zips = True
        # 只有从zip加载了新图库时才保存到数据库
        if loaded_from_zips:
            await self._save_to_db()

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
            compress_size=self.compress_size,
            match_mode=self.match_mode,
            dedup_enabled=self.dedup_enabled,
        )
        self.galleries[gallery.name] = gallery
        await self._save_to_db()
        return gallery

    async def load_gallery(self, gallery_info: dict) -> Gallery:
        """
        加载图库为实例
        :param gallery_info: 图库信息字典
        """
        # 确保保存的路径是绝对路径
        if "path" in gallery_info:
            from pathlib import Path
            gallery_info["path"] = str(Path(gallery_info["path"]).resolve())

        gallery = Gallery.from_dict(gallery_info)
        self.galleries[gallery.name] = gallery
        # 移除不必要的保存操作，避免每次加载都重写数据库
        # 只在有实际修改时才保存
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
        """
        根据图库名获取图库实例，支持别称解析
        :param name: 图库名或别称
        """
        # 1) 本名直接命中
        if name in self.galleries:
            return self.galleries[name]
        # 2) 别称匹配
        for gallery in self.galleries.values():
            if name in gallery.alias_list:
                return gallery
        return None

    def get_gallery_by_match_word(self, word: str) -> list[Gallery]:
        """
        根据给定的匹配词获取图库实例列表
        :param word: 匹配词
        :return: 满足条件的图库实例列表
        """
        return [
            gallery
            for gallery in self.galleries.values()
            if word in gallery.match_words
        ]

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

    # ----------------- 匹配词 / 匹配模式 -----------------

    async def set_match_mode(self, name: str, mode: str) -> str:
        """设置图库匹配模式（precise/fuzzy）"""
        if gallery := self.get_gallery(name):
            if gallery.set_match_mode(mode):
                await self._save_to_db()
                mode_str = "精准匹配" if mode == "precise" else "模糊匹配"
                return f"图库【{gallery.name}】已切换为：{mode_str}"
            return f"匹配模式错误：{mode}，仅支持 precise/fuzzy"
        return f"图库【{name}】不存在"

    async def add_match_words(self, name: str, words: list[str]) -> str:
        """为图库添加匹配词"""
        if gallery := self.get_gallery(name):
            added = gallery.add_match_words(words)
            await self._save_to_db()
            if added:
                return f"图库【{gallery.name}】新增匹配词：{added}\n当前匹配词：{gallery.match_words}"
            return f"图库【{gallery.name}】未新增匹配词（可能已存在）\n当前匹配词：{gallery.match_words}"
        return f"图库【{name}】不存在"

    async def remove_match_words(self, name: str, words: list[str]) -> str:
        """为图库删除匹配词"""
        if gallery := self.get_gallery(name):
            removed = gallery.remove_match_words(words)
            await self._save_to_db()
            if removed:
                return f"图库【{gallery.name}】已删除匹配词：{removed}\n当前匹配词：{gallery.match_words}"
            return f"图库【{gallery.name}】未删除匹配词（可能不存在）\n当前匹配词：{gallery.match_words}"
        return f"图库【{name}】不存在"

    # ----------------- 别称 -----------------

    async def set_alias(self, name: str, alias_list: list[str]) -> str:
        """设置图库别称（覆盖）"""
        if gallery := self.get_gallery(name):
            # 校验别称不能与其他图库的本名/别称冲突
            for a in alias_list:
                if a == gallery.name:
                    continue
                if self._alias_conflict(a, gallery):
                    return f"别称【{a}】已与其他图库冲突，无法设置"
            gallery.alias_list = [
                a for a in alias_list if a and a != gallery.name
            ]
            await self._save_to_db()
            return f"图库【{gallery.name}】别称已设为：{gallery.alias_list}"
        return f"图库【{name}】不存在"

    async def add_alias(self, name: str, alias_list: list[str]) -> str:
        """为图库添加别称"""
        if gallery := self.get_gallery(name):
            # 校验冲突
            blocked = [
                a for a in alias_list if a != gallery.name and self._alias_conflict(a, gallery)
            ]
            if blocked:
                return f"别称【{blocked}】已与其他图库冲突，无法添加"
            added = gallery.add_alias(alias_list)
            await self._save_to_db()
            if added:
                return f"图库【{gallery.name}】新增别称：{added}\n当前别称：{gallery.alias_list}"
            return f"图库【{gallery.name}】未新增别称（可能已存在）\n当前别称：{gallery.alias_list}"
        return f"图库【{name}】不存在"

    async def remove_alias(self, name: str, alias_list: list[str]) -> str:
        """为图库删除别称"""
        if gallery := self.get_gallery(name):
            removed = gallery.remove_alias(alias_list)
            await self._save_to_db()
            if removed:
                return f"图库【{gallery.name}】已删除别称：{removed}\n当前别称：{gallery.alias_list}"
            return f"图库【{gallery.name}】未删除别称（可能不存在）\n当前别称：{gallery.alias_list}"
        return f"图库【{name}】不存在"

    def _alias_conflict(self, alias: str, exclude: Gallery) -> bool:
        """检查别称是否与除 exclude 外的图库本名/别称冲突"""
        for g in self.galleries.values():
            if g is exclude:
                continue
            if alias == g.name or alias in g.alias_list:
                return True
        return False

    # ----------------- 去重 -----------------

    async def set_dedup(self, name: str, enabled: bool) -> str:
        """打开/关闭图库的去重开关"""
        if gallery := self.get_gallery(name):
            gallery.dedup_enabled = enabled
            await self._save_to_db()
            return f"图库【{gallery.name}】去重开关：{gallery.dedup_enabled}"
        return f"图库【{name}】不存在"

    async def deduplicate(self, name: str) -> str:
        """扫描并删除图库中重复的图片"""
        if gallery := self.get_gallery(name):
            removed = gallery.deduplicate()
            return f"图库【{gallery.name}】去重完成，共删除 {removed} 张重复图片"
        return f"图库【{name}】不存在"
