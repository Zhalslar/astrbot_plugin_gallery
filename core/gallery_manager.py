import asyncio
import json
import os
import aiofiles
from astrbot import logger
from .gallery import Gallery
from ..utils import unzip_file, zip_folder, move_files_up

class GalleryManager:
    """
    图库管理器类，负责管理所有图库的创建、删除和操作
    内部维护一个图库列表，用json文件存储图库信息
    """
    def __init__(
        self, galleries_dirs: list, json_file_path: str, default_gallery_info
    ):
        """
        初始化图库管理器
        :param json_file_path: 存储图库信息的JSON文件路径
        :param galleries_dir: 图库的根目录路径
        """
        self.json_file_path: str = json_file_path
        self.galleries_dirs: list[str] = galleries_dirs
        self.galleries = {}
        self.default_gallery_info = default_gallery_info.copy()
        self.exact_keywords = []
        self.fuzzy_keywords = []

    async def initialize(self):
        """
        初始化图库管理器
        """
        logger.info("图库管理器插件初始化中...")
        logger.debug(f"可用的图库总目录列表：{self.galleries_dirs}")

        await self._init_json_file()
        logger.debug("Json文件初始化完成")

        await self._load_json()
        logger.debug("从Json文件中加载实例完成")

        await self._load_new_folder()
        logger.debug("从新的文件夹中加载实例完成")

        await self.load_zips()
        logger.debug("从zip文件中加载实例完成")

        await self._update_keywords()
        logger.debug("匹配词更新完成")

        logger.info("图库管理器插件初始化完成，欢迎使用━(*｀∀´*)ノ亻!")


    async def _init_json_file(self):
        """
        初始化JSON文件，
        如果文件不存在，则创建一个空的JSON文件。
        如果文件存在但内容为空或不是有效的JSON列表
        """
        if not os.path.exists(self.json_file_path):
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
        (实际文件夹存在的图库才会被加载，不存在则会被删除信息)
        """
        if not os.path.exists(self.json_file_path):
            async with aiofiles.open(self.json_file_path, "r", encoding="utf-8") as file:
                data = await file.read()
            tasks = []
            for gallery_info in json.loads(data):
                if os.path.exists(gallery_info["path"]):
                    tasks.append(self.load_gallery(gallery_info))

            await asyncio.gather(*tasks)
            await self._save_galleries()

    async def _load_new_folder(self):
        """
        从新的文件夹中加载图库
        """
        for galleries_dir in self.galleries_dirs:
            for folder_name in os.listdir(galleries_dir):
                folder_path = os.path.join(galleries_dir, folder_name)
                # 确保是文件夹且未加载过的图库
                if os.path.isdir(folder_path) and folder_name not in self.galleries:
                    # 加载图库
                    self.default_gallery_info["path"] = folder_path
                    await self.load_gallery(self.default_gallery_info)

        await self._save_galleries()

    async def load_zips(self):
        """
        解压总图库文件夹中的ZIP文件，并加载为图库实例
        """
        for galleries_dir in self.galleries_dirs:
            for entry in os.scandir(galleries_dir):
                if entry.is_file() and entry.name.lower().endswith(".zip"):
                    zip_file = entry
                    folder_name = zip_file.name.rsplit(".", 1)[
                        0
                    ]  # 去除扩展名，获取文件夹名称
                    folder_path = os.path.join(galleries_dir, folder_name)

                    # 检查是否已存在同名文件夹
                    if any(
                        os.path.exists(os.path.join(galleries_dir, folder_name))
                        for galleries_dir in self.galleries_dirs
                    ):
                        logger.warning(
                            f"已存在同名文件夹【{folder_name}】，跳过解压ZIP文件：{zip_file.name}"
                        )
                        continue

                    logger.info(f"正在解压文件：{zip_file.name}")
                    if not unzip_file(zip_file.path, folder_path):
                        logger.error(f"解压失败，跳过文件: {zip_file.name}")
                        continue

                    # 删除ZIP文件
                    os.remove(zip_file.path)
                    logger.info(f"解压成功并自动删除了压缩包：{zip_file.name}")

                    # 确保解压目录存在且没有错误
                    if os.path.exists(folder_path):
                        # 解散可能存在的嵌套文件夹
                        move_files_up(folder_path)

                        # 加载为图库实例
                        self.default_gallery_info["path"] = folder_path
                        await self.load_gallery(self.default_gallery_info)
                    else:
                        logger.error(f"解压后的文件夹路径无效: {folder_path}")

    async def _update_keywords(self):
        """更新匹配词"""
        exact_keywords = []
        fuzzy_keywords = []

        for gallery in self.galleries.values():
            if gallery.fuzzy:
                fuzzy_keywords.extend(gallery.keywords)
            else:
                exact_keywords.extend(gallery.keywords)

        self.exact_keywords = exact_keywords
        self.fuzzy_keywords = fuzzy_keywords

    async def _save_galleries(self):
        """
        将当前管理的图库信息保存到JSON文件
        """
        await self._update_keywords()
        galleries_data = [gallery.to_dict() for gallery in self.galleries.values()]
        async with aiofiles.open(self.json_file_path, "w", encoding="utf-8") as file:
            await file.write(json.dumps(galleries_data, indent=4, ensure_ascii=False))

    async def compress_gallery(self, name: str) -> str | None:
        """
        将指定图库压缩为ZIP文件
        :param name: 图库名称
        """
        for galleries_dir in self.galleries_dirs:
            folder_path = os.path.join(galleries_dir, name)
            if os.path.exists(folder_path):
                zip_path = os.path.join(galleries_dir, f"{name}.zip")
                logger.info(f"正在将图库【{name}】压缩为ZIP文件")
                if not zip_folder(str(folder_path), str(zip_path)):
                    logger.error(f"压缩文件夹失败: {folder_path}")
                    return None
                logger.info(f"图库【{name}】已成功压缩为ZIP文件：{zip_path}")
                return zip_path
        return None

    async def load_gallery(self, gallery_info: dict) -> Gallery:
        """
        加载图库为实例
        :param gallery_info: 图库信息字典
        """
        gallery = Gallery(gallery_info)
        self.galleries[gallery.name] = gallery
        await self._save_galleries()
        return gallery

    async def delete_gallery(self, name: str) -> bool:
        """
        根据图库名删除图库
        :param gallery_name: 图库名
        """
        if name in self.galleries:
            gallery = self.galleries[name]
            gallery.delete()  # 删除图库文件夹
            del self.galleries[name]  # 从字典中删除图库实例
            await self._save_galleries()
            return True
        else:
            logger.error(f"图库不存在：{name}")
            return False

    def get_gallery(self, name: str) -> Gallery | None:
        """根据图库名获取图库实例"""
        return self.galleries.get(name)

    async def set_fuzzy(self, name: str, fuzzy: bool):
        """设置模糊匹配开关"""
        if gallery := self.get_gallery(name):
            gallery.fuzzy = fuzzy
            await self._save_galleries()
            return f"图库【{name}】模糊匹配：{fuzzy}"
        return f"图库【{name}】不存在"

    async def set_capacity(self, name: str, capacity: int):
        """设置图库容量上限"""
        if gallery := self.get_gallery(name):
            if capacity > 0:
                gallery.capacity = capacity
                await self._save_galleries()
                return f"图库【{name}】容量上限已设置为：{capacity}"
            else:
                return f"图库容量上限错误：{capacity}，必须大于0"
        return f"图库【{name}】不存在"

    async def set_compress(self, name: str, compress: bool):
        """设置图库新增图片时是否压缩"""
        if gallery := self.get_gallery(name):
            gallery.compress = compress
            await self._save_galleries()
            return f"图库【{gallery.name}】压缩开关: {gallery.compress}"
        return f"图库【{name}】不存在"

    async def set_duplicate(self, name: str, duplicate: bool):
        """设置图库新增图片时是否允许重复图片"""
        if gallery := self.get_gallery(name):
            gallery.duplicate = duplicate
            await self._save_galleries()
            return f"图库【{gallery.name}】去重开关: {gallery.duplicate}"
        return f"图库【{name}】不存在"

    async def add_keyword(self, name: str, keyword: str) -> str:
        """添加图库匹配词"""
        if gallery := self.get_gallery(name):
            if keyword not in gallery.keywords:
                gallery.keywords.append(keyword)
                await self._save_galleries()
                return f"图库【{gallery.name}】新增匹配词：{keyword}"
            else:
                return f"图库【{gallery.name}】已存在该匹配词"
        return f"图库【{name}】不存在"

    async def delete_keyword(self, name: str, keyword: str) -> str:
        """删除图库匹配词"""
        if gallery := self.get_gallery(name):
            if keyword in gallery.keywords:
                gallery.keywords.remove(keyword)
                await self._save_galleries()
                return f"已删除图库【{name}】的匹配词：{keyword}"
            else:
                return f"图库【{name}】不存在匹配词“{keyword}”"
        return f"图库【{name}】不存在"

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
    def get_gallery_by_keyword(self, keyword) -> list[Gallery]:
        """
        根据给定的匹配词获取图库实例列表
        :param keyword: 匹配词
        :return: 满足条件的图库实例列表
        """
        return [
            gallery for gallery in self.galleries.values() if keyword in gallery.keywords
        ]

    def get_all_galleries_names(self) -> list[str]:
        """
        获取所有图库的名称，组合成列表
        :return: 图库名称列表
        """
        return list(self.galleries.keys())
