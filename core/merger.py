import os
import time
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from astrbot.api import logger


class GalleryImageMerger:
    """图库图片合并器"""
    def __init__(self, thumb_size=(128, 128), delay=0.05):
        self.font_path = Path("data/plugins/astrbot_plugin_gallery/zzgf_dianhei.otf")
        self.thumbnail_size = thumb_size
        self.delay = delay

    def _process_image(self, img_path, sequence_number, font) -> Image.Image | None:
        try:
            img = Image.open(img_path)
            # GIF 取第一帧
            if img.format == "GIF":
                img.seek(0)
            # 转换为 RGB
            img = img.convert("RGB")
            # 缩放
            img = img.resize(self.thumbnail_size)

            draw = ImageDraw.Draw(img)

            # 文本尺寸
            bbox = draw.textbbox((0, 0), sequence_number, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            text_x = (self.thumbnail_size[0] - text_w) // 2
            text_y = self.thumbnail_size[1] - text_h - 1

            # 圆形背景
            radius = max(text_w, text_h) // 2 + 1

            circle_x1 = text_x - radius // 2
            circle_y1 = text_y
            circle_x2 = text_x + text_w + radius // 2
            circle_y2 = text_y + text_h // 2 + radius * 2 + 5

            draw.ellipse(
                [(circle_x1, circle_y1), (circle_x2, circle_y2)], fill=(255, 255, 255)
            )

            # 序号
            draw.text((text_x, text_y), sequence_number, font=font, fill=(0, 0, 0))

            return img

        except Exception as e:
            logger.error(f"加载图片 {img_path} 时出错：{e}")
            return None

    def create_merged(self, folder_path: str) -> bytes | None:
        thumb_w, thumb_h = self.thumbnail_size

        # 文件名排序
        image_files = sorted(
            [
                f
                for f in os.listdir(folder_path)
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif"))
            ],
            key=lambda x: int(x.split("_")[1]),
        )

        if not image_files:
            logger.warning("没有找到符合条件的图片文件")
            return None

        total = len(image_files)
        images_per_row = 5 if total <= 40 else 10

        # 合图宽度规则
        if total <= 5:
            width = thumb_w * total
        else:
            width = thumb_w * images_per_row

        height = thumb_h * ((total + images_per_row - 1) // images_per_row)

        merged = Image.new("RGB", (width, height), (255, 255, 255))

        font = ImageFont.truetype(self.font_path, 15)

        for idx, filename in enumerate(image_files):
            img_path = os.path.join(folder_path, filename)
            seq = filename.split("_")[1]

            img = self._process_image(img_path, seq, font)
            if img:
                x = (idx % images_per_row) * thumb_w
                y = (idx // images_per_row) * thumb_h
                merged.paste(img, (x, y))

            time.sleep(self.delay)

        out = BytesIO()
        merged.save(out, format="JPEG")
        return out.getvalue()
