import re
from io import BytesIO

import aiohttp
from PIL import ExifTags, Image

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig


class ImageInfoExtractor:
    """图片信息提取器"""

    # 中英文映射
    KEY_MAP = {
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
        "OffsetTimeDigitized": "数字化时区偏移",
        "ShutterSpeedValue": "快门速度值",
        "SensingMethod": "感光方法",
        "ExposureTime": "曝光时间",
        "FNumber": "F值",
        "ExposureProgram": "曝光程序",
        "ISOSpeedRatings": "ISO速度等级",
        "ISOSpeed": "ISO速度",
        "ExposureMode": "曝光模式",
        "LightSource": "光源",
        "FocalLengthIn35mmFilm": "35mm胶片焦距",
        "SceneCaptureType": "场景捕获类型",
        "FocalLength": "焦距",
        "Software": "软件",
        "SensitivityType": "敏感度类型",
        "RecommendedExposureIndex": "推荐曝光指数",
        "DigitalZoomRatio": "数字缩放比",
        "UserComment": "用户备注",
        "MakerNote": "制造商备注",
        "JpegIFOffset": "JPEG IF偏移量",
        "JpegIFByteCount": "JPEG IF字节数",
        "filter": "滤镜",
        "filterIntensity": "滤镜强度",
        "filterMask": "滤镜掩码",
        "captureOrientation": "拍摄方向",
        "highlight": "高光增强",
        "algolist": "算法列表",
        "multi-frame": "多帧合成",
        "brp_mask": "BRP掩码",
        "brp_del_th": "BRP阈值",
        "brp_del_sen": "BRP灵敏度",
        "motionLevel": "运动等级",
        "delta": "Delta变化",
        "module": "模块",
        "hw-remosaic": "重采样硬件",
        "touch": "触摸对焦点",
        "sceneMode": "场景模式",
        "cct_value": "色温值",
        "AI_Scene": "AI场景",
        "aec_lux": "曝光光照值",
        "aec_lux_index": "曝光指数",
        "HdrStatus": "HDR状态",
        "albedo": "反照率",
        "confidence": "置信度",
        "weatherinfo": "天气信息",
        "temperature": "温度",
        "fileterIntensity": "滤镜强度",
    }

    def __init__(self, config: AstrBotConfig):
        self.conf = config
        self.session = aiohttp.ClientSession()

    async def get_image_info(self, image: bytes) -> str | None:
        """对外统一入口：返回格式化后的图片信息字符串"""
        try:
            # 获取图片信息（扁平化）
            details = await self._get_image_details(image)
            # 中文转化
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
                # 处理GPS信息
                if "GPSInfo" in exif_info:
                    info["gps_info"] = await self._get_location(
                        exif_info.pop("GPSInfo")
                    )
                # 用户备注
                if "UserComment" in exif_info:
                    raw_comment = exif_info.pop("UserComment")
                    exif_info["UserComment"] = (
                        self._parse_and_join(raw_comment) or raw_comment
                    )
                # 转中文标签
                exif_chinese = {
                    self.KEY_MAP.get(tag, tag): value
                    for tag, value in exif_info.items()
                }
                info["exif"] = exif_chinese

            return info

    def _parse_and_join(self, text: str) -> str:
        """解析调试字符串 → 映射中文 → 拼接为一个整字符串"""
        result = {}

        # 按 ; 分割，过滤掉空字段
        parts = [p.strip() for p in text.split(";") if p.strip()]

        for part in parts:
            if ":" not in part:
                continue

            key, value = part.split(":", 1)
            key = key.strip()
            value = value.strip()

            # === 值解析 ===
            if value.lower() == "null" or value == "":
                value = None

            # (x, y) → tuple
            elif re.match(r"\(-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?\)", value):
                nums = re.findall(r"-?\d+\.?\d*", value)
                value = tuple(float(n) for n in nums)

            # 数字转换 → int/float
            else:
                if re.fullmatch(r"-?\d+", value):
                    value = int(value)
                elif re.fullmatch(r"-?\d+\.\d+", value):
                    value = float(value)

            # === 字段名中英文转换 ===
            cn_key = self.KEY_MAP.get(key, key)  # 没定义就用原英文
            result[cn_key] = value

        return "\n" + "\n".join(f"{k}: {v}" for k, v in result.items())

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

        return s.strip()

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

    @staticmethod
    def _dms2dec(dms, ref: str) -> float:
        deg, min, sec = dms
        dec = float(deg) + float(min) / 60 + float(sec) / 3600
        return -dec if ref in {"S", "W"} else dec

    def _parse_gps(self, info: dict):
        try:
            lat_dms, lat_ref = info[2], info[1]
            lon_dms, lon_ref = info[4], info[3]
            lat = self._dms2dec(lat_dms, lat_ref)
            lon = self._dms2dec(lon_dms, lon_ref)
            return lat, lon
        except (KeyError, TypeError, ZeroDivisionError) as e:
            logger.warning("GPS 解析失败: %s", e)
            return None, None

    async def _get_location(self, gps_info: dict) -> str | dict:
        try:
            lat, lon = self._parse_gps(gps_info)
            if lat is None or lon is None:  # 解析失败
                return gps_info  # 回退
        except Exception as e:
            logger.warning(f"GPS 解析失败: {e}")
            return gps_info  # 回退

        try:
            async with self.session.get(
                url="https://nominatim.openstreetmap.org/reverse",
                params={
                    "format": "json",
                    "lat": lat,
                    "lon": lon,
                    "zoom": 18,
                    "addressdetails": 1,
                },
                headers={"User-Agent": "AstrBot-GalleryPlugin/2.0.3"},
                proxy=self.conf["http_proxy"] or None,
                timeout=10,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("display_name") or gps_info
                else:
                    logger.warning(
                        f"逆地理编码失败 HTTP {resp.status} (Lat: {lat:.6f}, Lon: {lon:.6f})"
                    )
                    return gps_info  # 回退
        except Exception as e:
            logger.warning(f"获取地理位置网络异常: {e}")
            return gps_info

    async def close(self):
        await self.session.close()
