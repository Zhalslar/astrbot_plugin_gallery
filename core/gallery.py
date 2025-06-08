import asyncio
from datetime import datetime
import io
import os
import random
import re
import shutil
from PIL import Image
from astrbot import logger
from ..core.merge import create_merged_image

class Gallery:
    """
    图库类，包含图库的基本信息和操作方法
    """

    def __init__(self, gallery_info: dict):
        """
        初始化图库实例
        :param gallery_info: 图库信息字典
        :param galleries_dir: 图库的根目录路径
        """
        # 图库名, 图库名称不能重复，用于唯一标识图库
        self.name: str = os.path.basename(gallery_info["path"])
        # 图库路径
        self.path: str = gallery_info["path"]
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        # 图库创建者ID
        self.creator_id: str  = gallery_info.get("creator_id", "Unknown")
        # 图库创建者名称
        self.creator_name: str  = gallery_info.get("creator_name", "Unknown")
        # 图库创建时间
        self.creation_time: datetime = gallery_info.get("creation_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        # 图库容量上限
        self.capacity = min(gallery_info.get("capacity", 200), 9999)
        # 新增图片时是否压缩
        self.compress: bool = gallery_info.get("compress", False)
        # 是否允许重复图片
        self.duplicate: bool = gallery_info.get("duplicate", True)
        # 是否模糊匹配
        self.fuzzy: bool = gallery_info.get("fuzzy", False)
        # 触发图库的关键词列表，默认关键词为图库名称
        self.keywords: list[str] = gallery_info.get("keywords", [self.name])
        # 异步处理图片文件名
        asyncio.create_task(self._specify_names())

    def to_dict(self):
        """
        将图库实例转换为字典，方便保存到JSON文件
        """
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
        """
        处理图库文件夹中的图片文件名，使其符合命名格式
        """
        image_files = self._get_images()
        for image_file in image_files:
             # 检查文件名是否符合指定格式
            if not re.match(r"^[^_]+_\d+_[^_]+\.\w+$", image_file.name):
                with open(image_file, "rb") as f:
                    image = f.read()
                label = self._filter_text(image_file.name)
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
                # 加入延时操作，避免高负载时造成性能问题
                await asyncio.sleep(0.1)

    def _get_images(self) -> list[os.DirEntry]:
        """
        获取目录下所有图片文件的目录条目（`os.DirEntry`），
        只考虑扩展名匹配的图片文件。
        """
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}
        image_entries = []
        with os.scandir(self.path) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.lower().endswith(
                    tuple(image_extensions)
                ):
                    image_entries.append(entry)
        return image_entries

    def _get_image_names(self) -> list[str]:
        """获取图库中所有图片的文件名"""
        return [entry.name for entry in self._get_images()]


    def _generate_name(
        self, image: bytes, label: str, index: int = 0
    ):
        """
        生成图片名称，根据图片的字节数据、标签和序号生成文件名。
        如果未指定序号，则自动生成一个唯一的序号。
        """
        # 获取图片格式
        with Image.open(io.BytesIO(image)) as img:
            extension = img.format.lower() if img.format else "jpg"

        # 如果未指定图片序号，则自动生成唯一的序号
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

        # 生成图片文件名
        return f"{self.name}_{index}_{label}.{extension}"


    def add_image(self, image: bytes, label: str, index: int = 0) -> str:
        """传递bytes，添加图片到图库"""
        name = self._generate_name(image, label, index)
        images = self._get_images()

        # 不能超过图库容量上限
        if len(list(images)) >= self.capacity:
            return f"图库【{self.name}】容量已满"

        if self.need_compress(image):
            if result := self.compress_image(image):  # 压缩图片
                image = result

        if self.duplicate:
            for img in images:
                with open(img.path, "rb") as file:
                    if file.read() == image:
                        return f"图库【{self.name}】中已存在该图片"

        path = os.path.join(self.path, name)
        with open(path, "wb") as f:
            f.write(image)
        return f"图库【{self.name}】新增图片：\n{name}"

    def delete(self):
        """删除图库对应的文件夹"""
        abs_path = os.path.abspath(self.path)
        if os.path.exists(abs_path):
            shutil.rmtree(abs_path)

    def delete_image_by_index(self, index: str|int) -> str:
        """删除图库中的图片
        :param index: 图片索引
        """
        names = self._get_image_names()
        if not names:
            return f"图库【{self.name}】为空"
        name = next((n for n in names if n.split("_")[1] == str(index)), None)
        if name:
            image_path = os.path.join(self.path, name)
            os.remove(image_path)
            return f"图库【{self.name}】已删除图片：\n{name}"
        else:
            return f"图库【{self.name}】中不存在图{index} "


    def view_by_index(self, index: int|str) -> str:
        """以序号查找图库中的图片"""
        names = self._get_image_names()
        if not names:
            return f"图库【{self.name}】为空"
        name = next((n for n in names if n.split("_")[1] == str(index)), None)
        if name:
            return os.path.join(self.path, name)
        else:
            return f"图库【{self.name}】中不存在图{index} "

    def view_by_bytes(self, image: bytes) -> str:
        """以bytes查找图库中的图片"""
        for file in self._get_images():
            if file.is_file():
                with open(file, "rb") as file:
                    if file.read() == image:
                        return file.name
        return f"图库【{self.name}】中没有这张图"

    def preview(self) -> str | bytes:
        """查看图库预览图"""
        merged_image_bytes = create_merged_image(str(self.path))
        if not merged_image_bytes:
            return f"图库【{self.name}】为空"
        else:
            return merged_image_bytes

    def get_random_image(self) -> str|None:
        "随机获取图库中的一张图片,返回图片路径"
        images = self._get_images()
        return random.choice(images).path if images else None


    def remove_duplicates(self):
        """删除图库中的重复图片"""
        names = self._get_image_names()
        unique_images = set()
        duplicates = []
        for name in names:
            path = os.path.join(self.path, name)
            with open(path, "rb") as file:
                image = file.read()
                if image in unique_images:
                    duplicates.append(name)
                else:
                    unique_images.add(image)
        for duplicate in duplicates:
            (self.path / duplicate).unlink()
            logger.info(f"删除重复图片：{duplicate}，图库：{self.name}")


    def need_compress(self, image: bytes, max_size: int = 512) -> bool:
        """判断图片是否需要压缩"""
        if self.compress is False:
            return False
        img = Image.open(io.BytesIO(image))
        if img.format == "GIF":
            return False
        if img.width > max_size or img.height > max_size:
            return True
        return False

    @staticmethod
    def compress_image(image_bytes: bytes, max_size: int = 512) -> bytes | None:
        """压缩图片到max_size大小，gif不处理"""
        image = Image.open(io.BytesIO(image_bytes))
        try:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            output = io.BytesIO()
            image.save(output, format=image.format)
            output.seek(0)
            return output.getvalue()

        except Exception as e:
            logger.error(f"压缩图片失败：{e}")
            return

    @staticmethod
    def _filter_text(text: str) -> str:
        """过滤字符，只保留中文、数字和字母, 并截短非数字字符串"""
        f_str = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", text)
        return f_str[: 10] if not f_str.isdigit() else f_str



