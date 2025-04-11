
from io import BytesIO
from PIL import Image, ExifTags
from astrbot import logger

# EXIF标签到中文名称的映射表
exif_tag_to_chinese = {
    "ImageWidth": "图像宽度",
    "ImageLength": "图像长度",
    "GPSInfo": "GPS信息",
    "ResolutionUnit": "分辨率单位",
    "ExifOffset": "EXIF偏移量",
    "Make": "制造商",
    "Model": "型号",
    "Orientation": "方向",
    "DateTime": "日期时间",
    "YCbCrPositioning": "YCbCr定位",
    "XResolution": "X方向分辨率",
    "YResolution": "Y方向分辨率",
    "ExifVersion": "EXIF版本",
    "SceneType": "场景类型",
    "ApertureValue": "光圈值",
    "ColorSpace": "颜色空间",
    "ExposureBiasValue": "曝光偏差",
    "MaxApertureValue": "最大光圈值",
    "ExifImageHeight": "EXIF图像高度",
    "BrightnessValue": "亮度值",
    "DateTimeOriginal": "原始日期时间",
    "FlashPixVersion": "FlashPix版本",
    "WhiteBalance": "白平衡",
    "ExifInteroperabilityOffset": "EXIF互操作性偏移量",
    "Flash": "闪光灯",
    "ExifImageWidth": "EXIF图像宽度",
    "ComponentsConfiguration": "组件配置",
    "MeteringMode": "测光模式",
    "OffsetTime": "时区偏移",
    "SubsecTimeOriginal": "原始亚秒时间",
    "SubsecTime": "亚秒时间",
    "SubsecTimeDigitized": "数字化亚秒时间",
    "OffsetTimeOriginal": "原始时区偏移",
    "DateTimeDigitized": "数字化日期时间",
    "ShutterSpeedValue": "快门速度值",
    "SensingMethod": "感光方法",
    "ExposureTime": "曝光时间",
    "FNumber": "F值",
    "ExposureProgram": "曝光程序",
    "ISOSpeedRatings": "ISO速度等级",
    "ExposureMode": "曝光模式",
    "LightSource": "光源",
    "FocalLengthIn35mmFilm": "35mm胶片焦距",
    "SceneCaptureType": "场景捕获类型",
    "FocalLength": "焦距",
    "MakerNote": "制造商备注",
}


async def get_image_details(image: bytes) -> dict:
    """获取图片的详细信息"""

    with Image.open(BytesIO(image)) as img:
        # 获取基本信息
        image_info = {
            "actual_format": img.format,
            "size": img.size,
            "file_size": get_image_storage_size(image),
            "mode": img.mode,
        }
        # 获取DPI信息
        dpi = img.info.get("dpi")
        if dpi:
            image_info["dpi"] = dpi
        # 获取缩略图信息
        thumb = img.info.get("thumbnail")
        if thumb:
            image_info["thumbnail"] = {"size": thumb.size, "mode": thumb.mode}
        # 获取EXIF信息
        if hasattr(img, "_getexif"):
            exif_data = img._getexif() # type: ignore
            if exif_data:
                # 将EXIF标签转换为中文名称
                exif_info = {
                    ExifTags.TAGS.get(k, k): v
                    for k, v in exif_data.items()
                    if k in ExifTags.TAGS
                }
                # 使用映射表将EXIF标签转换为中文
                exif_info_chinese = {
                    exif_tag_to_chinese.get(tag, tag): value
                    for tag, value in exif_info.items()
                }
                image_info["exif"] = exif_info_chinese
        # 获取GPS信息
        if "exif" in image_info and "GPSInfo" in image_info["exif"]:
            image_info["gps_info"] = image_info["exif"].pop("GPSInfo")

        return image_info


def format_image_details(info) -> str:
    """将图片信息字典汉化，重新整理格式返回字符串，增强易读性"""
    info_str = "【图片信息】：\n"
    # 基本信息
    info_str += f"格式: {info.get('actual_format')}\n"

    info_str += f"尺寸: {info.get('size')}\n"

    info_str += f"大小: {info.get('file_size')}\n"

    info_str += f"颜色模式: {info.get('mode')}"
    # DPI信息
    dpi = info.get("dpi")
    if dpi:
        info_str += f"\nDPI: {dpi}"
    # 缩略图信息
    thumbnail = info.get("thumbnail")
    if thumbnail:
        info_str += f"\n缩略图信息: 尺寸 {thumbnail.get('size')}，颜色模式 {thumbnail.get('mode')}"
    # GPS信息
    gps_info = info.get("gps_info")
    if gps_info:
        info_str += "\nGPS信息: "
        info_str += str(gps_info)
    # EXIF信息
    exif_info = info.get("exif")
    if exif_info:
        info_str += "\n"
        for tag, value in exif_info.items():
            info_str += f"{tag}: {value}\n"
    return info_str


def get_image_storage_size(img_bytes: bytes) -> str:
    """获取图片的存储大小，并处理单位"""
    if img_bytes is None:
        logger.warning("无法获取空的内存字节流的存储大小")
        return ""
    storage_size_str = ""
    storage_size = len(img_bytes)
    if storage_size > 1024 * 1024:
        file_size_mb = storage_size / (1024 * 1024)
        storage_size_str += f"{file_size_mb:.2f} MB"
    else:
        file_size_kb = storage_size / 1024
        storage_size_str += f"{file_size_kb:.2f} KB"
    return storage_size_str


async def get_image_info(image: bytes) -> str|None:
    """获取图片信息"""
    try:
        image_info = await get_image_details(image)
        image_info_str = format_image_details(image_info)
        return image_info_str
    except Exception as e:
        logger.error(f"获取图片信息失败: {e}")
        return None
