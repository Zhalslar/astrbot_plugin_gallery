import asyncio
import io
import os
import random
import re
import shutil
from datetime import datetime

from PIL import Image

from astrbot import logger

from ..utils import compress_image, filter_text


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
        tags: list[str] | None = None,
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
        self.tags = tags or []

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
            tags=d.get("tags", [os.path.basename(d["path"])]),
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
            "tags": self.tags,
        }

    def to_str(self):
        return (
            f"图库名称：{self.name}\n"
            f"图库路径：{self.path}\n"
            f"创建者ID：{self.creator_id}\n"
            f"创建之人：{self.creator_name}\n"
            f"创建时间：{self.creation_time}\n"
            f"容量上限：{self.capacity}\n"
            f"已用容量：{len(os.listdir(self.path))}\n"
            f"压缩图片：{self.compress}\n"
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

    def _get_images(self) -> list[os.DirEntry]:
        """获取图片文件"""
        with os.scandir(self.path) as entries:
            return [
                entry
                for entry in entries
                if entry.is_file() and entry.name.lower().endswith(tuple(self.EXT))
            ]

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

    def add_image(self, image: bytes, author: str = "default", index: int = 0) -> tuple[bool, str]:
        """添加图片"""
        img_name = self._generate_name(image, author, index)
        images = self._get_images()

        if len(images) >= self.capacity:
            return False, f"图库【{self.name}】容量已满"

        if self.compress:
            result = compress_image(image, max_size = 512)
            if result:
                image = result

        for img in images:
            with open(img.path, "rb") as file:
                if file.read() == image:
                    return False, f"图库【{self.name}】中已存在该图片"

        try:
            with open(os.path.join(self.path, img_name), "wb") as f:
                f.write(image)
        except Exception as e:
            return False, f"保存图片时发生错误：{str(e)}"

        return True, f"图库【{self.name}】新增图片：\n{img_name}"

    def delete(self):
        """删除图库"""
        abs_path = os.path.abspath(self.path)
        if os.path.exists(abs_path):
            shutil.rmtree(abs_path)

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


