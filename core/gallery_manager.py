import asyncio
import json
from pathlib import Path

import aiofiles
from astrbot import logger
from .gallery import Gallery


class GalleryManager:
    """
    图库管理器类，负责管理所有图库的创建、删除和操作
    内部维护一个图库列表，用json文件存储图库信息
    """

    def __init__(self, galleries_dir: Path, json_file_path: Path, default_gallery_info):
        """
        初始化图库管理器
        :param json_file_path: 存储图库信息的JSON文件路径
        :param galleries_dir: 图库的根目录路径
        """
        self.json_file_path: Path = json_file_path
        self.galleries_dir: Path = galleries_dir
        self.galleries_dir.mkdir(parents=True, exist_ok=True)
        self.galleries = {}
        self.default_gallery_info = default_gallery_info

    async def initialize(self):
        """
        初始化图库管理器
        """
        logger.info("开始初始化图库管理器")
        await self._init_json_file()
        logger.info("Json文件初始化完成")
        await self._load_json()
        logger.info("图库实例化完成")
        await self._sync_with_filesystem()
        logger.info("图库与文件系统同步完成")

    async def _init_json_file(self):
        """
        初始化JSON文件，
        如果文件不存在，则创建一个空的JSON文件。
        如果文件存在但内容为空或不是有效的JSON列表
        """
        if not self.json_file_path.exists():
            async with aiofiles.open(
                self.json_file_path, "w", encoding="utf-8"
            ) as file:
                await file.write("[]")
        else:
            try:
                async with aiofiles.open(
                    self.json_file_path, "r", encoding="utf-8"
                ) as file:
                    data = await file.read()
                galleries_data = json.loads(data)
                if not isinstance(galleries_data, list):
                    raise ValueError("文件内容不是列表格式")
            except (json.JSONDecodeError, ValueError):
                logger.error("图库信息文件已损坏")

    async def _load_json(self):
        """
        从JSON文件加载图库信息并创建图库实例
        """
        if self.json_file_path.exists():
            async with aiofiles.open(
                self.json_file_path, "r", encoding="utf-8"
            ) as file:
                data = await file.read()
            galleries_data = json.loads(data)

            tasks = [
                self._create_gallery_instance(gallery_info)
                for gallery_info in galleries_data
            ]
            await asyncio.gather(*tasks)

    async def _sync_with_filesystem(self):
        """
        将实例与文件夹同步：
        - 添加文件夹中有但实例中没有的图库
        - 删除实例中有但文件夹不存在的图库
        """
        # 当前图库实例的名称集合
        current_gallery_names = set(self.galleries.keys())

        # 实际文件夹名称集合
        actual_folder_names = {
            folder.name for folder in self.galleries_dir.iterdir() if folder.is_dir()
        }

        # 添加新增的文件夹为图库实例
        for folder_name in actual_folder_names - current_gallery_names:
            gallery_info = self.default_gallery_info.copy()
            gallery_info["name"] = folder_name
            await self.add_gallery(gallery_info)
            logger.info(f"已加载新图库文件夹为实例：{folder_name}")

        # 删除不存在文件夹的图库实例
        for gallery_name in current_gallery_names - actual_folder_names:
            await self.delete_gallery(gallery_name)
            logger.warning(f"已删除失效图库实例：{gallery_name}")

        await self.save_galleries()

    def is_image_file(self, file: Path):
        """
        判断文件是否为图片
        """
        return file.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}

    async def _create_gallery_instance(self, gallery_info):
        """
        创建图库实例
        """
        gallery = Gallery(gallery_info, self.galleries_dir)
        self.galleries[gallery.name] = gallery

    async def save_galleries(self):
        """
        将当前管理的图库信息保存到JSON文件
        """
        galleries_data = [gallery.to_dict() for gallery in self.galleries.values()]
        async with aiofiles.open(self.json_file_path, "w", encoding="utf-8") as file:
            await file.write(json.dumps(galleries_data, indent=4, ensure_ascii=False))

    async def add_gallery(self, gallery_info: dict) -> Gallery:
        """
        添加新的图库
        :param gallery_info: 图库信息字典
        """
        gallery_name = gallery_info["name"]
        if gallery_name not in self.galleries:
            gallery = Gallery(gallery_info, self.galleries_dir)
            self.galleries[gallery.name] = gallery
            await self.save_galleries()
            return gallery
        return self.galleries[gallery_name]

    async def delete_gallery(self, gallery_name: str) -> bool:
        """
        根据图库名删除图库
        :param gallery_name: 图库名
        """
        if gallery_name in self.galleries:
            gallery = self.galleries[gallery_name]
            gallery.delete()  # 删除图库文件夹
            del self.galleries[gallery_name]  # 从字典中删除图库实例
            await self.save_galleries()
            return True
        else:
            logger.error(f"图库不存在：{gallery_name}")
            return False

    def get_gallery(self, gallery_name: str) -> Gallery | None:
        """
        根据图库名获取图库实例
        :param gallery_name: 图库名
        :return: Gallery实例
        """
        return self.galleries.get(gallery_name)

    def list_galleries(self) -> list[dict]:
        """
        返回所有图库的基本信息
        :return: 图库信息列表
        """
        return [gallery.to_dict() for gallery in self.galleries.values()]

    async def set_password(self, gallery_name: str, password: str):
        """设置图库访问密码"""
        if gallery := self.get_gallery(gallery_name):
            gallery.password = password
            logger.info(f"图库访问密码：{password}")
            await self.save_galleries()
            return f"图库【{gallery_name}】密码已设置为：{password}"
        return f"图库【{gallery_name}】不存在"

    async def set_fuzzy_match(self, gallery_name: str, fuzzy_match: bool):
        """设置模糊匹配开关"""
        if gallery := self.get_gallery(gallery_name):
            gallery.fuzzy_match = fuzzy_match
            await self.save_galleries()
            return f"图库【{gallery_name}】模糊匹配：{fuzzy_match}"
        return f"图库【{gallery_name}】不存在"

    async def set_max_capacity(self, gallery_name: str, max_capacity: int):
        """设置图库容量上限"""
        if gallery := self.get_gallery(gallery_name):
            if max_capacity > 0:
                gallery.max_capacity = max_capacity
                await self.save_galleries()
                return f"图库【{gallery_name}】容量上限已设置为：{max_capacity}"
            else:
                return f"图库容量上限错误：{max_capacity}，必须大于0"
        return f"图库【{gallery_name}】不存在"

    async def set_compress_switch(self, gallery_name: str, compress: bool):
        """设置图库新增图片时是否压缩"""
        if gallery := self.get_gallery(gallery_name):
            gallery.compress_switch = compress
            await self.save_galleries()
            return f"图库【{gallery.name}】压缩开关: {gallery.compress_switch}"
        return f"图库【{gallery_name}】不存在"

    async def set_duplicate_switch(self, gallery_name: str, duplicate: bool):
        """设置图库新增图片时是否允许重复图片"""
        if gallery := self.get_gallery(gallery_name):
            gallery.duplicate_switch = duplicate
            await self.save_galleries()
            return f"图库【{gallery.name}】去重开关: {gallery.duplicate_switch}"
        return f"图库【{gallery_name}】不存在"

    async def add_keyword(self, gallery_name: str, keyword: str) -> str:
        """添加图库匹配词"""
        if gallery := self.get_gallery(gallery_name):
            if keyword not in gallery.keywords:
                gallery.keywords.append(keyword)
                await self.save_galleries()
                return f"图库【{gallery.name}】新增匹配词：{keyword}"
            else:
                return f"图库【{gallery.name}】已存在该匹配词"
        return f"图库【{gallery_name}】不存在"

    async def delete_keyword(self, gallery_name: str, keyword: str) -> str:
        """删除图库匹配词"""
        if gallery := self.get_gallery(gallery_name):
            if keyword in gallery.keywords:
                gallery.keywords.remove(keyword)
                await self.save_galleries()
                return f"已删除图库【{gallery_name}】的匹配词：{keyword}"
            else:
                return f"图库【{gallery_name}】不存在匹配词“{keyword}”"
        return f"图库【{gallery_name}】不存在"

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

    def get_fuzzy_match_keywords(self) -> list[str]:
        """
        获取所有模糊匹配的图库的关键词，组合成列表
        :return: 关键词列表
        """
        keywords = []
        for gallery in self.galleries.values():
            if gallery.fuzzy_match:
                keywords.extend(gallery.keywords)
        return keywords

    def get_exact_match_keywords(self) -> list[str]:
        """
        获取所有精准匹配的图库的关键词，组合成列表
        :return: 关键词列表
        """
        keywords = []
        for gallery in self.galleries.values():
            if not gallery.fuzzy_match:
                keywords.extend(gallery.keywords)
        return keywords

    def get_all_galleries_names(self) -> list[str]:
        """
        获取所有图库的名称，组合成列表
        :return: 图库名称列表
        """
        return list(self.galleries.keys())
