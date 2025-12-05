from io import BytesIO

from PIL import ExifTags, Image

from astrbot.api import logger


class ImageInfoExtractor:
    """图片信息提取器"""

    # EXIF 标签中文映射
    EXIF_TAG_MAP = {
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

    async def get_image_info(self, image: bytes) -> str | None:
        """对外统一入口：返回格式化后的图片信息字符串"""
        try:
            details = await self._get_image_details(image)
            return self._format_details(details)
        except Exception as e:
            logger.error(f"获取图片信息失败: {e}")
            return None

    # =============================
    #           内部函数
    # =============================

    async def _get_image_details(self, img_bytes: bytes) -> dict:
        """提取图片的详细信息"""

        with Image.open(BytesIO(img_bytes)) as img:
            info = {
                "actual_format": img.format,
                "size": img.size,
                "file_size": self._get_storage_size(img_bytes),
                "mode": img.mode,
            }

            # DPI
            dpi = img.info.get("dpi")
            if dpi:
                info["dpi"] = dpi

            # 内置缩略图
            thumb = img.info.get("thumbnail")
            if thumb:
                info["thumbnail"] = {"size": thumb.size, "mode": thumb.mode}

            # EXIF
            exif_data = getattr(img, "_getexif", lambda: None)()
            if exif_data:
                exif_info = {
                    ExifTags.TAGS.get(k, k): v
                    for k, v in exif_data.items()
                    if k in ExifTags.TAGS
                }
                # 转中文标签
                exif_chinese = {
                    self.EXIF_TAG_MAP.get(tag, tag): value
                    for tag, value in exif_info.items()
                }
                info["exif"] = exif_chinese

            # GPS 单独抠出来
            if "exif" in info and "GPSInfo" in info["exif"]:
                info["gps_info"] = info["exif"].pop("GPSInfo")

            return info

    def _format_details(self, info: dict) -> str:
        """将图片信息整理为可读文本"""

        s = "【图片信息】：\n"
        s += f"格式: {info.get('actual_format')}\n"
        s += f"尺寸: {info.get('size')}\n"
        s += f"大小: {info.get('file_size')}\n"
        s += f"颜色模式: {info.get('mode')}"

        if dpi := info.get("dpi"):
            s += f"\nDPI: {dpi}"

        if thumb := info.get("thumbnail"):
            s += f"\n缩略图: 尺寸 {thumb['size']}，模式 {thumb['mode']}"

        if gps := info.get("gps_info"):
            s += f"\nGPS信息: {gps}"

        if exif := info.get("exif"):
            s += "\n"
            for k, v in exif.items():
                s += f"{k}: {v}\n"

        return s

    def _get_storage_size(self, img_bytes: bytes) -> str:
        """字节大小转 KB/MB"""

        if not img_bytes:
            logger.warning("无法获取图片大小（bytes为空）")
            return ""

        size = len(img_bytes)

        if size > 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / 1024:.2f} KB"
