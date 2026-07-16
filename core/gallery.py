import asyncio
import io
import os
import random
import re
import shutil
from datetime import datetime

from PIL import Image

from astrbot import logger

from ..utils import (
    calculate_dhash,
    compress_image,
    filter_text,
    hamming_distance,
    is_similar_image,
)


class Gallery:
    """
    图库类，用于管理单个图库
    """

    EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}

    def __init__(
        self,
        path: str,
        name: str | None = None,
        creator_id: str = "Unknown",
        creator_name: str = "Unknown",
        creation_time: str | None = None,
        capacity: int = 200,
        compress: bool = False,
        compress_size: int = 512,
        tags: list[str] | None = None,
        match_mode: str = "fuzzy",
        match_words: list[str] | None = None,
        dedup_enabled: bool = True,
        alias_list: list[str] | None = None,
    ):
        self.path = path
        os.makedirs(self.path, exist_ok=True)

        self.name = name or os.path.basename(path)

        self.creator_id = creator_id
        self.creator_name = creator_name
        self.creation_time = creation_time or datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.capacity = min(capacity, 9999)
        self.compress = compress
        self.compress_size = compress_size
        self.tags = tags or []
        # 精准匹配 / 模糊匹配
        self.match_mode = match_mode if match_mode in ("precise", "fuzzy") else "fuzzy"
        # 匹配词列表（精准模式下生效）
        self.match_words = match_words or []
        # 去重开关：控制 add_image 时是否检查重复图片
        self.dedup_enabled = dedup_enabled
        # 别称列表：可被这些名字引用
        self.alias_list = alias_list or []
        # dhash 缓存：图片文件名 -> dhash 字符串（用于近似判重）
        self.dhash_cache: dict[str, str] = {}

        asyncio.create_task(self._specify_names())


    @classmethod
    def from_dict(cls, d: dict):
        """工厂方法: 从字典中创建图库对象"""
        return cls(
            path=d["path"],
            creator_id=d.get("creator_id", "Unknown"),
            creator_name=d.get("creator_name", "Unknown"),
            creation_time=d.get("creation_time"),
            capacity=d.get("capacity", 200),
            compress=d.get("compress", False),
            compress_size=d.get("compress_size", 512),
            tags=d.get("tags", [os.path.basename(d["path"])]),
            match_mode=d.get("match_mode", "fuzzy"),
            match_words=d.get("match_words", []),
            dedup_enabled=d.get("dedup_enabled", True),
            alias_list=d.get("alias_list", []),
        )

    def to_dict(self):
        return {
            "name": self.name,
            "path": self.path,
            "creator_id": self.creator_id,
            "creator_name": self.creator_name,
            "creation_time": self.creation_time,
            "capacity": self.capacity,
            "compress": self.compress,
            "compress_size": self.compress_size,
            "tags": self.tags,
            "match_mode": self.match_mode,
            "match_words": self.match_words,
            "dedup_enabled": self.dedup_enabled,
            "alias_list": self.alias_list,
        }

    def to_str(self):
        return (
            f"图库名称：{self.name}\n"
            f"图库别称：{self.alias_list}\n"
            f"图库路径：{self.path}\n"
            f"创建者ID：{self.creator_id}\n"
            f"创建之人：{self.creator_name}\n"
            f"创建时间：{self.creation_time}\n"
            f"容量上限：{self.capacity}\n"
            f"已用容量：{len(os.listdir(self.path))}\n"
            f"压缩图片：{self.compress}\n"
            f"图库去重：{self.dedup_enabled}\n"
            f"匹配模式：{self.match_mode}\n"
            f"匹配词表：{self.match_words}\n"
            f"图库标签： {self.tags}"
        )

    async def _specify_names(self):
        """规范化图片名称"""
        for image_file in self._get_images():
            if not re.match(r"^[^_]+_\d+_[^_]+\.\w+$", image_file.name):
                with open(image_file.path, "rb") as f:
                    image = f.read()
                author = filter_text(image_file.name)
                new_name = self._generate_name(image, author)
                if new_name != image_file.name:
                    try:
                        new_path = os.path.join(self.path, new_name)
                        os.rename(image_file.path, new_path)
                        logger.info(f"图片文件名更新：{image_file.name} -> {new_name}")
                    except Exception as e:
                        logger.error(
                            f"重命名图片失败：{image_file.name} -> {new_name}，错误：{e}"
                        )
                    await asyncio.sleep(0.1)

    async def _build_dhash_cache(self):
        """构建 dhash 缓存（异步，在初始化时调用）"""
        for img in self._get_images():
            try:
                with open(img.path, "rb") as f:
                    img_bytes = f.read()
                dhash = calculate_dhash(img_bytes)
                if dhash:
                    self.dhash_cache[img.name] = dhash
            except Exception as e:
                logger.warning(f"计算 {img.name} dhash 失败：{e}")

    def _get_images(self) -> list[os.DirEntry]:
        """获取图片文件"""
        with os.scandir(self.path) as entries:
            return [
                entry
                for entry in entries
                if entry.is_file() and entry.name.lower().endswith(tuple(self.EXT))
            ]

    def check_similar_image(
        self, image: bytes, threshold: int = 5
    ) -> tuple[bool, str | None]:
        """
        检测相似图片（基于 dhash 汉明距离）
        
        Args:
            image: 待检测图片字节
            threshold: 相似度阈值（汉明距离 ≤ 此值视为相似）
        
        Returns:
            (is_similar, similar_image_name)
        """
        # 1. 计算新图片 dhash
        new_dhash = calculate_dhash(image)
        if not new_dhash:
            return False, None
        
        # 2. 遍历现有图片对比
        for img_name, cached_dhash in self.dhash_cache.items():
            if is_similar_image(new_dhash, cached_dhash, threshold):
                return True, img_name
        
        return False, None

    def _get_image_names(self) -> list[str]:
        """获取图片名称"""
        return [entry.name for entry in self._get_images()]

    def _generate_name(self, image: bytes, author: str = "", index: int = 0) -> str:
        """生成图片名称"""
        with Image.open(io.BytesIO(image)) as img:
            if img.format is None:
                logger.warning(
                    "Image format could not be detected. Defaulting to 'jpg'."
                )
                extension = "jpg"
            else:
                extension = img.format.lower()

        if index == 0:
            names = self._get_image_names()
            existing_numbers = [
                int(name.split("_")[1])
                for name in names
                if len(name.split("_")) > 1 and name.split("_")[1].isdigit()
            ]
            index = 1
            while index in existing_numbers:
                index += 1

        return f"{self.name}_{index}_{author}.{extension}"

    def add_image(self, image: bytes, author: str = "default", index: int = 0, skip_similar_check: bool = False) -> tuple[bool, str]:
        """添加图片
        
        Args:
            image: 图片字节
            author: 作者名
            index: 序号（用于替换）
            skip_similar_check: 跳过相似检测（用户确认上传时用）
        """
        img_name = self._generate_name(image, author, index)
        images = self._get_images()

        if len(images) >= self.capacity:
            return False, f"图库【{self.name}】容量已满"

        if self.compress:
            if result := compress_image(image, max_size=self.compress_size):
                image = result

        # 仅在开启去重时检查重复
        if self.dedup_enabled:
            for img in images:
                with open(img.path, "rb") as file:
                    if file.read() == image:
                        return False, f"图库【{self.name}】中已存在该图片"

        try:
            with open(os.path.join(self.path, img_name), "wb") as f:
                f.write(image)
            
            # 更新 dhash 缓存
            dhash = calculate_dhash(image)
            if dhash:
                self.dhash_cache[img_name] = dhash
        except Exception as e:
            return False, f"保存图片时发生错误：{str(e)}"

        return True, f"图库【{self.name}】新增图片：\n{img_name}"

    def delete(self):
        """删除图库"""
        abs_path = os.path.abspath(self.path)
        if os.path.exists(abs_path):
            shutil.rmtree(abs_path)

    # ----------------- 匹配词 / 匹配模式 -----------------

    def add_match_words(self, words: list[str]) -> list[str]:
        """添加匹配词（去重）"""
        added = []
        for w in words:
            if w and w not in self.match_words:
                self.match_words.append(w)
                added.append(w)
        return added

    def remove_match_words(self, words: list[str]) -> list[str]:
        """删除匹配词"""
        removed = []
        for w in words:
            if w in self.match_words:
                self.match_words.remove(w)
                removed.append(w)
        return removed

    def set_match_mode(self, mode: str) -> bool:
        """设置匹配模式：precise / fuzzy"""
        if mode not in ("precise", "fuzzy"):
            return False
        self.match_mode = mode
        return True

    def match(self, text: str) -> bool:
        """精准匹配：消息包含任一匹配词即命中"""
        if not text:
            return False
        return any(w and w in text for w in self.match_words)

    # ----------------- 别称 -----------------

    def add_alias(self, alias_list: list[str]) -> list[str]:
        """添加别称（去重，且不能与本名/已有图库名冲突）"""
        added = []
        for a in alias_list:
            if a and a != self.name and a not in self.alias_list:
                self.alias_list.append(a)
                added.append(a)
        return added

    def remove_alias(self, alias_list: list[str]) -> list[str]:
        """删除别称"""
        removed = []
        for a in alias_list:
            if a in self.alias_list:
                self.alias_list.remove(a)
                removed.append(a)
        return removed

    # ----------------- 去重扫描 -----------------

    def deduplicate(self) -> int:
        """
        扫描图库并删除重复图片（基于内容字节）
        :return: 删除的图片数量
        """
        images = self._get_images()
        seen: set[int] = set()
        removed = 0
        for img in images:
            try:
                with open(img.path, "rb") as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"读取图片失败：{img.name}，错误：{e}")
                continue
            digest = hash(content)
            if digest in seen:
                os.remove(img.path)
                removed += 1
            else:
                seen.add(digest)
        return removed

    def delete_image_by_index(self, index: str | int) -> tuple[bool, str]:
        """通过索引删除图片"""
        names = self._get_image_names()
        if not names:
            return False, f"图库【{self.name}】为空"
        name = next((n for n in names if n.split("_")[1] == str(index)), None)
        if name:
            os.remove(os.path.join(self.path, name))
            return True, f"图库【{self.name}】已删除图片：\n{name}"
        return False, f"图库【{self.name}】中不存在图{index}"

    def view_by_index(self, index: str | int) -> tuple[bool, str | os.PathLike]:
        """通过索引查看图片"""
        names = self._get_image_names()
        if not names:
            return False, f"图库【{self.name}】为空"
        name = next((n for n in names if n.split("_")[1] == str(index)), None)
        if name:
            return True, os.path.join(self.path, name)
        return False, f"图库【{self.name}】中不存在图{index}"

    def view_by_bytes(self, image: bytes) -> tuple[bool, str | os.PathLike]:
        """通过字节查看图片"""
        for file in self._get_images():
            with open(file.path, "rb") as f:
                if f.read() == image:
                    return True, file.name
        return False, f"图库【{self.name}】中没有这张图"

    def get_random_image(self) -> tuple[bool, str | os.PathLike]:
        """获取一张随机图片"""
        images = self._get_images()
        if not images:
            return False, f"图库【{self.name}】为空"
        return True, random.choice(images).path


