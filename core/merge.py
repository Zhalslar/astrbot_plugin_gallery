import os
from io import BytesIO
from pathlib import Path
import time

from PIL import Image, ImageDraw, ImageFont

RESOURCE_DIR: Path = Path("data/plugins/astrbot_plugin_gallery") / "resource"
FONT_PATH: Path = RESOURCE_DIR / "msyh.ttf"


def process_image(img_path, sequence_number, font, thumbnail_size) -> Image.Image|None:
    try:
        # 打开图片并转换为RGBA模式
        img = Image.open(img_path).convert("RGBA")

        # 如果是GIF，取第一帧
        if img.format == "GIF":
            img.seek(0)

        # 缩放到指定尺寸
        img = img.resize(thumbnail_size)

        # 创建一个可以在给定图像上绘图的对象
        draw = ImageDraw.Draw(img)

        # 使用 textbbox 获取序号文本的边界框
        bbox_seq = draw.textbbox((0, 0), sequence_number, font=font)

        # 计算文本的宽度和高度
        text_width = bbox_seq[2] - bbox_seq[0]
        text_height = bbox_seq[3] - bbox_seq[1]

        # 计算文本的居中位置
        text_x = (thumbnail_size[0] - text_width) // 2
        text_y = thumbnail_size[1] - text_height - 15  # 序号距离图片底部15像素

        # 计算圆形背景的半径
        radius = max(text_width, text_height) // 2 + 1  # 给圆形增加一些间距

        # 计算圆形背景的上下边界
        circle_x1 = text_x - radius // 2
        circle_y1 = text_y
        circle_x2 = text_x + text_width + radius // 2
        circle_y2 = text_y + text_height // 2 + radius * 2 + 5

        # 绘制半透明白色圆形背景
        draw.ellipse(
            [(circle_x1, circle_y1), (circle_x2, circle_y2)],
            fill=(255, 255, 255, 230),  # 半透明白色背景
        )

        # 在图片中下方绘制序号，颜色为黑色
        draw.text((text_x, text_y), sequence_number, font=font, fill=(0, 0, 0))

        return img
    except Exception as e:
        print(f"加载图片 {img_path} 时出错：{e}")
        return None


def create_merged_image(folder_path: str) -> bytes|None:
    # 图片缩放尺寸
    thumbnail_size = (128, 128)

    font_size = 25  # 设置序号字号为25

    # 获取文件夹内所有图片文件名，并按序号排序
    image_files = sorted(
        [
            f
            for f in os.listdir(folder_path)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif"))
        ],
        key=lambda x: int(x.split("_")[1]),
    )

    # 检查是否有图片文件
    if not image_files:
        print("没有找到符合条件的图片文件，请检查文件夹路径和文件格式。")
        return None

    # 根据图片数量决定每行显示的图片数量
    images_per_row = 5 if len(image_files) <= 40 else 10

    # 初始化合成图的宽度和高度
    if len(image_files) <= 5:
        width = thumbnail_size[0] * len(image_files)
    else:
        width = thumbnail_size[0] * images_per_row

    height = thumbnail_size[1] * (
        len(image_files) // images_per_row
        + (1 if len(image_files) % images_per_row != 0 else 0)
    )

    merged_image = Image.new(
        "RGBA", (width, height), (255, 255, 255, 0)
    )  # 使用 RGBA 模式

    font = ImageFont.truetype(str(FONT_PATH), font_size)

    # 顺序处理图片，避免并行带来的高CPU占用
    for i, image_file in enumerate(image_files):
        img_path = os.path.join(folder_path, image_file)
        sequence_number = image_file.split("_")[1]

        img = process_image(img_path, sequence_number, font, thumbnail_size)
        if img:
            x = (i % images_per_row) * thumbnail_size[0]
            y = (i // images_per_row) * thumbnail_size[1]

            merged_image.paste(img, (x, y))

        # 延时，减少CPU负载
        time.sleep(0.05)

    byte_arr = BytesIO()
    merged_image.save(byte_arr, format="PNG")
    return byte_arr.getvalue()
