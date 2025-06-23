import asyncio
import io
import os
import random
import re
import shutil
from datetime import datetime
from PIL import Image
from astrbot import logger
from data.plugins.astrbot_plugin_gallery.utils import filter_text
from ..core.merge import create_merged_image
from .gallery_result import GalleryResult, ResultType


class Gallery:
    def __init__(self, gallery_info: dict):
        self.name: str = os.path.basename(gallery_info["path"])
        self.path: str = gallery_info["path"]
        os.makedirs(self.path, exist_ok=True)

        self.creator_id: str = gallery_info.get("creator_id", "Unknown")
        self.creator_name: str = gallery_info.get("creator_name", "Unknown")
        self.creation_time: str = gallery_info.get(
            "creation_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        self.capacity = min(gallery_info.get("capacity", 200), 9999)
        self.compress: bool = gallery_info.get("compress", False)
        self.duplicate: bool = gallery_info.get("duplicate", True)
        self.fuzzy: bool = gallery_info.get("fuzzy", False)
        self.keywords: list[str] = gallery_info.get("keywords", [self.name])

        asyncio.create_task(self._specify_names())

    def to_dict(self):
        return {
            "name": self.name,
            "path": self.path,
            "creator_id": self.creator_id,
            "creator_name": self.creator_name,
            "creation_time": self.creation_time,
            "capacity": self.capacity,
            "compress": self.compress,
            "duplicate": self.duplicate,
            "fuzzy": self.fuzzy,
            "keywords": self.keywords,
        }

    async def _specify_names(self):
        for image_file in self._get_images():
            if not re.match(r"^[^_]+_\d+_[^_]+\.\w+$", image_file.name):
                with open(image_file.path, "rb") as f:
                    image = f.read()
                label = filter_text(image_file.name)
                new_name = self._generate_name(image, label)
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
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}
        with os.scandir(self.path) as entries:
            return [
                entry
                for entry in entries
                if entry.is_file()
                and entry.name.lower().endswith(tuple(image_extensions))
            ]

    def _get_image_names(self) -> list[str]:
        return [entry.name for entry in self._get_images()]

    def _generate_name(self, image: bytes, label: str, index: int = 0) -> str:
        with Image.open(io.BytesIO(image)) as img:
            if img.format is None:
                logger.warning("Image format could not be detected. Defaulting to 'jpg'.")
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

        return f"{self.name}_{index}_{label}.{extension}"

    def add_image(self, image: bytes, label: str, index: int = 0) -> GalleryResult:
        name = self._generate_name(image, label, index)
        images = self._get_images()

        if len(images) >= self.capacity:
            return GalleryResult(False, ResultType.TEXT, f"图库【{self.name}】容量已满")

        if self.need_compress(image):
            result = self.compress_image(image)
            if result:
                image = result

        if self.duplicate:
            for img in images:
                with open(img.path, "rb") as file:
                    if file.read() == image:
                        return GalleryResult(
                            False, ResultType.TEXT, f"图库【{self.name}】中已存在该图片"
                        )

        try:
            with open(os.path.join(self.path, name), "wb") as f:
                f.write(image)
        except Exception as e:
            return GalleryResult(
                False, ResultType.TEXT, f"保存图片时发生错误：{str(e)}"
            )

        return GalleryResult(
            True, ResultType.TEXT, f"图库【{self.name}】新增图片：\n{name}"
        )

    def delete(self):
        abs_path = os.path.abspath(self.path)
        if os.path.exists(abs_path):
            shutil.rmtree(abs_path)

    def delete_image_by_index(self, index: str | int) -> GalleryResult:
        names = self._get_image_names()
        if not names:
            return GalleryResult(False, ResultType.TEXT, f"图库【{self.name}】为空")
        name = next((n for n in names if n.split("_")[1] == str(index)), None)
        if name:
            os.remove(os.path.join(self.path, name))
            return GalleryResult(
                True, ResultType.TEXT, f"图库【{self.name}】已删除图片：\n{name}"
            )
        return GalleryResult(
            False, ResultType.TEXT, f"图库【{self.name}】中不存在图{index}"
        )

    def view_by_index(self, index: str | int) -> GalleryResult:
        names = self._get_image_names()
        if not names:
            return GalleryResult(False, ResultType.TEXT, f"图库【{self.name}】为空")
        name = next((n for n in names if n.split("_")[1] == str(index)), None)
        if name:
            return GalleryResult(
                True, ResultType.IMAGE_PATH, os.path.join(self.path, name)
            )
        return GalleryResult(
            False, ResultType.TEXT, f"图库【{self.name}】中不存在图{index}"
        )

    def view_by_bytes(self, image: bytes) -> GalleryResult:
        for file in self._get_images():
            with open(file.path, "rb") as f:
                if f.read() == image:
                    return GalleryResult(True, ResultType.TEXT, file.name)
        return GalleryResult(False, ResultType.TEXT, f"图库【{self.name}】中没有这张图")

    def preview(self) -> GalleryResult:
        result = create_merged_image(self.path)
        if not result:
            return GalleryResult(False, ResultType.TEXT, f"图库【{self.name}】为空")
        return GalleryResult(True, ResultType.IMAGE_BYTES, result)

    def get_random_image(self) -> GalleryResult:
        images = self._get_images()
        if not images:
            return GalleryResult(False, ResultType.TEXT, f"图库【{self.name}】为空")
        return GalleryResult(True, ResultType.IMAGE_PATH, random.choice(images).path)

    def remove_duplicates(self):
        names = self._get_image_names()
        unique_images = set()
        for name in names:
            path = os.path.join(self.path, name)
            with open(path, "rb") as file:
                data = file.read()
                if data in unique_images:
                    os.remove(path)
                    logger.info(f"删除重复图片：{name}，图库：{self.name}")
                else:
                    unique_images.add(data)

    def need_compress(self, image: bytes, max_size: int = 512) -> bool:
        if not self.compress:
            return False
        with Image.open(io.BytesIO(image)) as img:
            return img.format != "GIF" and (
                img.width > max_size or img.height > max_size
            )

    @staticmethod
    def compress_image(image_bytes: bytes, max_size: int = 512) -> bytes | None:
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format=image.format)
                return output.getvalue()
        except Exception as e:
            logger.error(f"压缩图片失败：{e}")
            return None
