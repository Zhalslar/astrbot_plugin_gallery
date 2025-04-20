from datetime import datetime
import io
import json
from pathlib import Path
import random
from typing import Dict
from PIL import Image
from astrbot import logger
from ..core.merge import create_merged_image

# 图库数据存储路径
GALLERIES_DIR = Path("data/plugins_data") / "astrbot_plugin_gallery"
# 存储图库信息的 JSON 文件
RESOURCE_DIR: Path = Path(__file__).resolve().parent / "resource"
GALLERIES_INFO_FILE = RESOURCE_DIR / "gallery_info.json"

SUPERUSERS = ["123456789"]  # 超级用户列表


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
        self.password: str  = gallery_info.get("password", "114514")
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

    def __str__(self):
        """返回图库的详细信息"""
        return (
            f"图库名称：{self.name}\n"
            f"图库路径：{self.path}\n"
            f"创建者ID：{self.creator_id}\n"
            f"创建者名称：{self.creator_name}\n"
            f"创建时间：{self.creation_time}\n"
            f"容量上限：{self.max_capacity}\n"
            f"是否压缩图片：{self.compress_switch}\n"
            f"是否允许重复：{self.duplicate_switch}\n"
            f"是否模糊匹配：{self.fuzzy_match}\n"
            f"图库匹配词：{self.keywords}"
        )

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

    def set_password(self, password: str):
        """设置图库访问密码"""
        self.password = password
        logger.info(f"图库访问密码：{password}")


    def set_max_capacity(self, max_capacity: int):
        """设置图库容量上限"""
        if max_capacity > 0:
            self.max_capacity = max_capacity
            logger.info(f"图库容量上限：{max_capacity}")
        else:
            logger.error(f"图库容量上限错误：{max_capacity}，必须大于0")

    def set_compress_switch(self, compress_switch: bool):
        """设置图库新增图片时是否压缩"""
        self.compress_switch = compress_switch


    def set_duplicate_switch(self, duplicate_switch: bool):
        """设置图库新增图片时是否允许重复图片"""
        self.duplicate_switch = duplicate_switch


    def add_keyword(self, keyword: str) -> str:
        """添加图库匹配词"""
        if keyword not in self.keywords:
            self.keywords.append(keyword)
            return f"图库【{self.name}】新增匹配词：{keyword}"
        else:
            return f"图库【{self.name}】已存在该匹配词"

    def delete_keyword(self, keyword: str) -> str:
        """删除图库匹配词"""
        if keyword in self.keywords:
            self.keywords.remove(keyword)
            return f"已删除图库【{self.name}】的匹配词“{keyword}”"
        else:
            return f"图库【{self.name}】不存在匹配词“{keyword}”"

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

    def check_permitted(self, user_label: str, user_id: str | None = None) -> bool:
        """检查用户是否有权限访问图库"""
        if user_id and user_id in SUPERUSERS:
            return True
        if self.path.is_dir():
            return user_label == self.path.name
        if not self.path.exists() or not self.path.is_file():
            return False
        return False
        # pattern = r"^(?P<gallery_name>[^_]+)_(?P<number>\d+)_(?P<label>[^.]+)\.[^.]+$"
        # match = re.match(pattern, self.path.name)
        # if not match:
        #     return False
        # return user_label == match.group("gallery_name") or user_label == match.group(
        #     "label"
        # )

    def _generate_image_name(self, image_bytes: bytes, image_label: str):
        """生成图片名称"""
        # 获取拓展名
        with Image.open(io.BytesIO(image_bytes)) as img:
            extension = img.format.lower() if img.format else "jpg"

        #  以图片编号生成唯一的图片文件名，取用最小的可用编号
        existing_numbers = set()
        for file in self.path.iterdir():
            if file.is_file():
                parts = file.stem.split("_")
                if parts[1].isdigit():
                    existing_numbers.add(int(parts[1]))
        pic_num = 1
        while pic_num in existing_numbers:
            pic_num += 1
        return f"{self.name}_{pic_num}_{image_label}.{extension}"

    def add_image(self, image_bytes: bytes, image_label: str) -> str:
        """传递bytes，添加图片到图库"""
        image_name = self._generate_image_name(image_bytes, image_label)

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



class GalleryManager:
    """
    图库管理器类，负责管理所有图库的创建、删除和操作
    内部维护一个图库列表，用json文件存储图库信息
    """

    def __init__(self, galleries_dir: Path, json_file_path: Path):
        """
        初始化图库管理器
        :param json_file_path: 存储图库信息的JSON文件路径
        :param galleries_dir: 图库的根目录路径
        """
        self.json_file_path: Path = json_file_path
        self.galleries_dir: Path = galleries_dir
        self.galleries: Dict[str, Gallery] = {}  # 使用字典存储图库实例，键为gallery.name
        self._init_json_file()  # 初始化JSON文件
        self._init_galleries()  # 初始化图库文件夹
        self._load_json()

    def _init_json_file(self):
            """
            初始化JSON文件，
            如果文件不存在，则创建一个空的JSON文件。
            如果文件存在但内容为空或不是有效的JSON列表，则重置为一个空列表。
            """
            # 检查文件是否存在
            if not self.json_file_path.exists():
                # 如果文件不存在，创建一个包含空列表的JSON文件
                with open(self.json_file_path, "w", encoding="utf-8") as file:
                    json.dump([], file, indent=4, ensure_ascii=False)
            else:
                # 如果文件存在，尝试读取并验证内容
                try:
                    with open(self.json_file_path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                    # 确保文件内容是一个列表
                    if not isinstance(data, list):
                        raise ValueError("文件内容不是列表格式")
                except (json.JSONDecodeError, ValueError):
                    # 如果文件内容为空、损坏或不是列表，重置为一个空列表
                    with open(self.json_file_path, "w", encoding="utf-8") as file:
                        json.dump([], file, indent=4, ensure_ascii=False)


    def _load_json(self):
        """
        从JSON文件加载图库信息并创建图库实例
        """
        if self.json_file_path.exists():
            with open(self.json_file_path, "r", encoding="utf-8") as file:
                galleries_data = json.load(file)
            for gallery_info in galleries_data:
                gallery = Gallery(gallery_info, self.galleries_dir)
                self.galleries[gallery.name] = gallery

    def _init_galleries(self):
        """
        初始化图库文件夹，
        确保“总目录->子目录->图片”结构，
        同时删除非图片文件和空子目录，
        加载图库实例
        """
        self.galleries_dir.mkdir(parents=True, exist_ok=True)
        # 遍历总目录
        for item in self.galleries_dir.iterdir():
            # 确保总目录下一级全为子目录
            if not item.is_dir():
                item.unlink()
            # 确保子目录下全为图片
            for file in item.iterdir():
                if not self.is_image_file(file):
                    file.unlink()
            # 将文件夹加载成图库实例
            self.galleries
            gallery_info = {"name": item.name}
            self.add_gallery(gallery_info)


    def is_image_file(self, file_path: Path) -> bool:
        """
        定义哪些扩展名被认为是图片
        :param file_path: 文件路径
        :return: 是否为图片文件
        """
        if not file_path.is_file():
            return False
        image_extensions = {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".webp",
            ".tiff",
            ".ico",
        }
        return file_path.suffix.lower() in image_extensions


    def save_galleries(self):
        """
        将当前管理的图库信息保存到JSON文件
        """
        galleries_data = [gallery.to_dict() for gallery in self.galleries.values()]
        with open(self.json_file_path, "w", encoding="utf-8") as file:
            json.dump(galleries_data, file, indent=4, ensure_ascii=False)

    def add_gallery(self, gallery_info: dict) -> Gallery | None:
        """
        添加新的图库
        :param gallery_info: 图库信息字典
        """
        if gallery_info["name"] not in [gallery.name for gallery in self.galleries.values()]:
            gallery = Gallery(gallery_info, self.galleries_dir)
            self.galleries[gallery.name] = gallery
            self.save_galleries()
            return gallery

    def delete_gallery(self, gallery_name: str) -> bool:
        """
        根据图库名删除图库
        :param gallery_name: 图库名
        """
        if gallery_name in self.galleries:
            gallery = self.galleries[gallery_name]
            gallery.delete()  # 删除图库文件夹
            del self.galleries[gallery_name] # 从字典中删除图库实例
            self.save_galleries()
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

    def get_gallery_by_name(self, name: str) -> Gallery | None:
        """
        根据图库名称获取图库实例
        :param name: 图库名称
        :return: Gallery实例
        """
        return self.galleries.get(name)
    def get_gallery_by_keyword(self, keyword: str) -> list[Gallery]:
        """
        根据关键词获取图库实例列表
        :param keyword: 关键词
        :return: Gallery实例列表
        """
        return [
            gallery for gallery in self.galleries.values() if keyword in gallery.keywords
        ]
    def get_gallery_by_creator(self, creator_id: str) -> list[Gallery]:
        """
        根据创建者ID获取图库实例列表
        :param creator_id: 创建者ID
        :return: Gallery实例列表
        """
        return [
            gallery for gallery in self.galleries.values() if gallery.creator_id == creator_id
        ]
    def get_gallery_by_password(self, password: str) -> list[Gallery]:
        """
        根据密码获取图库实例列表
        :param password: 密码
        :return: Gallery实例列表
        """
        return [
            gallery for gallery in self.galleries.values() if gallery.password == password
        ]
    def get_gallery_by_fuzzy_match(self, fuzzy_match: bool) -> list[Gallery]:
        """
        根据模糊匹配获取图库实例列表
        :param fuzzy_match: 模糊匹配开关
        :return: Gallery实例列表
        """
        return [
            gallery for gallery in self.galleries.values() if gallery.fuzzy_match == fuzzy_match
        ]
    def get_gallery_by_compress_switch(self, compress_switch: bool) -> list[Gallery]:
        """
        根据压缩开关获取图库实例列表
        :param compress_switch: 压缩开关
        :return: Gallery实例列表
        """
        return [
            gallery for gallery in self.galleries.values() if gallery.compress_switch == compress_switch
        ]
    def get_gallery_by_duplicate_switch(self, duplicate_switch: bool) -> list[Gallery]:
        """
        根据重复开关获取图库实例列表
        :param duplicate_switch: 重复开关
        :return: Gallery实例列表
        """
        return [
            gallery for gallery in self.galleries.values() if gallery.duplicate_switch == duplicate_switch
        ]
    def get_gallery_by_creation_time(self, creation_time: datetime) -> list[Gallery]:
        """
        根据创建时间获取图库实例列表
        :param creation_time: 创建时间
        :return: Gallery实例列表
        """
        return [
            gallery for gallery in self.galleries.values() if gallery.creation_time == creation_time
        ]
    def get_gallery_by_creator_name(self, creator_name: str) -> list[Gallery]:
        """
        根据创建者名称获取图库实例列表
        :param creator_name: 创建者名称
        :return: Gallery实例列表
        """
        return [
            gallery for gallery in self.galleries.values() if gallery.creator_name == creator_name
        ]
    def get_gallery_by_keywords(self, keywords: list[str]) -> list[Gallery]:
        """
        根据关键词获取图库实例列表
        :param keywords: 关键词列表
        :return: Gallery实例列表
        """
        return [
            gallery for gallery in self.galleries.values() if any(keyword in gallery.keywords for keyword in keywords)
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
