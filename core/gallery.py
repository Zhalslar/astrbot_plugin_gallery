import asyncio
from datetime import datetime
import io
from pathlib import Path
import random
import re
from PIL import Image
from astrbot import logger
from ..core.merge import create_merged_image

class Gallery:
    """
    图库类，包含图库的基本信息和操作方法
    """

    def __init__(self, gallery_info: dict, galleries_dir: Path):
        """
        初始化图库实例
        :param gallery_info: 图库信息字典
        :param galleries_dir: 图库的根目录路径
        """
        # 图库名, 图库名称不能重复，用于唯一标识图库
        self.name: str  = gallery_info.get("name", "Unknown")
        # 图库路径
        self.path: Path  = galleries_dir / self.name
        # 图库创建者ID
        self.creator_id: str  = gallery_info.get("creator_id", "Unknown")
        # 图库创建者名称
        self.creator_name: str  = gallery_info.get("creator_name", "Unknown")
        # 图库创建时间
        self.creation_time: datetime = gallery_info.get("creation_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        # 访问密码
        self.password: str  = gallery_info.get("password", "0")
        # 图库容量上限
        self.max_capacity: int = gallery_info.get("max_capacity", 200)
        # 新增图片时是否压缩
        self.compress_switch: bool = gallery_info.get("compress_switch", False)
        # 是否允许重复图片
        self.duplicate_switch: bool = gallery_info.get("duplicate_switch", True)
        # 是否模糊匹配
        self.fuzzy_match: bool = gallery_info.get("fuzzy_match", False)
        # 触发图库的关键词列表，默认关键词为图库名称
        self.keywords: list[str] = gallery_info.get("keywords", [self.name])
        # 初始化图库目录
        self.path.mkdir(parents=True, exist_ok=True)
        # 异步处理图片文件名
        asyncio.create_task(self._process_images_async())

    def to_dict(self):
        """
        将图库实例转换为字典，方便保存到JSON文件
        """
        return {
            "name": self.name,
            "path": str(self.path),
            "creator_id": self.creator_id,
            "creator_name": self.creator_name,
            "creation_time": self.creation_time,
            "password": self.password,
            "max_capacity": self.max_capacity,
            "compress_switch": self.compress_switch,
            "duplicate_switch": self.duplicate_switch,
            "fuzzy_match": self.fuzzy_match,
            "keywords": self.keywords,
        }

    async def _process_images_async(self):
        """
        异步处理图库文件夹中的图片文件名，使其符合命名格式
        """
        image_files = [img for img in self.path.iterdir() if img.is_file()]
        for image_file in image_files:
             # 检查文件名是否符合指定格式
            if not re.match(r"^[^_]+_\d+_[^_]+\.\w+$", image_file.name):
                with open(image_file, "rb") as f:
                    image_bytes = f.read()
                new_name = self._generate_image_name(image_bytes, image_label="system")
                if new_name != image_file.name:
                    try:
                        new_path = self.path / new_name
                        image_file.rename(new_path)
                        logger.info(f"图片文件名更新：{image_file.name} -> {new_name}")
                    except Exception as e:
                        logger.error(
                            f"重命名图片失败：{image_file.name} -> {new_name}，错误：{e}"
                        )
                # 加入延时操作，避免高负载时造成性能问题
                await asyncio.sleep(0.1)

    def delete(self) -> bool:
        """删除图库"""
        if self.path.exists():
            for child in self.path.iterdir():
                child.unlink()
            self.path.rmdir()
            return True
        else:
            logger.error(f"图库不存在：{self.name}")
            return False

    def delete_image_by_index(self, index: str|int) -> str:
        """删除图库中的图片
        :param index: 图片索引
        """
        image_names = [img.name for img in self.path.iterdir() if img.is_file()]
        if not image_names:
            return f"图库【{self.name}】为空"
        selected_image = next(
            (img for img in image_names if img.split("_")[1] == str(index)), None
        )
        if selected_image:
            image_path = self.path / selected_image
            image_path.unlink()
            return f"已删除：{selected_image}"
        else:
            return f"图库【{self.name}】中不存在图{index} "

    def get_image_names(self) -> str:
        """获取图库中的所有图片的名称"""
        if self.path.exists():
            image_names = [img.name for img in self.path.iterdir() if img.is_file()]
            if not image_names:
                return f"图库【{self.name}】为空"
            else:
                return "\n".join(image_names).strip()
        else:
            return f"图库【{self.name}】不存在"

    def preview(self) -> str | bytes:
        """查看图库预览图"""
        if self.path.exists():
            merged_image_bytes = create_merged_image(str(self.path))
            if not merged_image_bytes:
                return f"图库【{self.name}】为空"
            else:
                return merged_image_bytes
        else:
            return f"图库【{self.name}】不存在"


    def _generate_image_name(
        self, image_bytes: bytes, image_label: str, index: int = 0
    ):
        """
        生成图片名称，根据图片的字节数据、标签和序号生成文件名。
        如果未指定序号，则自动生成一个唯一的序号。
        """
        # 获取图片格式
        with Image.open(io.BytesIO(image_bytes)) as img:
            extension = img.format.lower() if img.format else "jpg"

        # 如果未指定图片序号，则自动生成唯一的序号
        if index == 0:
            existing_numbers = [
                int(file.stem.split("_")[1])
                for file in self.path.iterdir()
                if file.is_file()
                and len(file.stem.split("_")) > 1
                and file.stem.split("_")[1].isdigit()
            ]
            index = 1
            while index in existing_numbers:
                index += 1

        # 生成图片文件名
        return f"{self.name}_{index}_{image_label}.{extension}"

    def add_image(self, image_bytes: bytes, image_label: str, index: int = 0) -> str:
        """传递bytes，添加图片到图库"""
        image_name = self._generate_image_name(image_bytes, image_label, index)

        # 不能超过图库容量上限
        if len(list(self.path.iterdir())) >= self.max_capacity:
            return f"图库【{self.name}】容量已满"

        if self.compress_switch:
            if result := self.compress_image(image_bytes):  # 压缩图片
                image_bytes = result

        if self.path.exists():
            image_path = self.path / image_name
            with open(image_path, "wb") as f:
                f.write(image_bytes)
            return f"图库【{self.name}】新增图片：\n{image_name}"
        else:
            return f"图库【{self.name}】不存在"

    def delete_image(self, image_name: str) -> str:
        """删除图库中的图片"""
        if self.path.exists():
            image_path = self.path / image_name
            if image_path.exists():
                image_path.unlink()
                return f"已删除图片：{image_name}"
            else:
                return f"图库【{self.name}】中没有这张图"
        else:
            return f"图库【{self.name}】不存在"

    def view_by_index(self, index: int|str) -> str | Path:
        """以序号查找图库中的图片"""
        image_names = [img.name for img in self.path.iterdir() if img.is_file()]
        if not image_names:
            return f"图库【{self.name}】为空"
        selected_image = next(
            (img for img in image_names if img.split("_")[1] == str(index)), None
        )
        if selected_image:
            image_path = self.path / selected_image
            return image_path
        else:
            return f"图库【{self.name}】中不存在图{index} "

    def view_by_bytes(self, image: bytes) -> str:
        """以bytes查找图库中的图片"""
        if self.path.exists():
            for file in self.path.iterdir():
                if file.is_file():
                    with open(file, "rb") as file:
                        if file.read() == image:
                            return file.name
            return f"图库【{self.name}】中没有这张图"
        else:
            return f"图库【{self.name}】不存在"

    def get_random_image(self) -> Path|None:
        "随机获取图库中的一张图片,返回图片路径"
        files = [file for file in self.path.iterdir() if file.is_file()]
        return random.choice(files) if files else None

    def find_duplicate(self, image: bytes) -> str:
        """检查图库中是否有重复图片"""
        for filename in self.path.iterdir():
            if filename.is_file():
                with open(filename, "rb") as file:
                    if file.read() == image:
                        return filename.name
        return f"图库【{self.name}】中没找到重复图片"

    def remove_duplicates(self):
        """删除图库中的重复图片"""
        if self.path.exists():
            image_names = [img.name for img in self.path.iterdir() if img.is_file()]
            unique_images = set()
            duplicates = []
            for image_name in image_names:
                with open(self.path / image_name, "rb") as file:
                    image_bytes = file.read()
                    if image_bytes in unique_images:
                        duplicates.append(image_name)
                    else:
                        unique_images.add(image_bytes)
            for duplicate in duplicates:
                (self.path / duplicate).unlink()
                logger.info(f"删除重复图片：{duplicate}，图库：{self.name}")
                return f"图库【{self.name}】删除重复图片：{duplicate}"
        else:
            return f"图库【{self.name}】不存在"

    @staticmethod
    def compress_image(image_bytes: bytes, max_size: int = 512) -> bytes | None:
        """压缩图片到max_size大小，gif不处理"""
        try:
            img = Image.open(io.BytesIO(image_bytes))
            if img.format == "GIF":
                return
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            output = io.BytesIO()
            img.save(output, format=img.format)
            output.seek(0)
            return output.getvalue()

        except Exception as e:
            logger.error(f"压缩图片失败：{e}")
            return

