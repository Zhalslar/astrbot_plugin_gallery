
import json
import os

import aiofiles

from astrbot import logger


class GalleryDB:
    """
    数据库抽象层：现在用 JSON，实现后可无缝切换到 SQLite / Redis
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        """初始化 JSON 存储文件"""
        if not os.path.exists(self.db_path):
            async with aiofiles.open(self.db_path, "w", encoding="utf-8") as f:
                await f.write("[]")
            return

        try:
            async with aiofiles.open(self.db_path, encoding="utf-8") as f:
                data = await f.read()
            parsed = json.loads(data)
            if not isinstance(parsed, list):
                raise ValueError
        except Exception:
            logger.error("图库 JSON 文件损坏，重新初始化为空列表")
            async with aiofiles.open(self.db_path, "w", encoding="utf-8") as f:
                await f.write("[]")

    async def load_all(self) -> list[dict]:
        """读出所有图库信息（返回 dict 列表）"""
        if not os.path.exists(self.db_path):
            return []

        async with aiofiles.open(self.db_path, encoding="utf-8") as f:
            raw = await f.read()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("JSON 解析失败，返回空列表")
            return []

    async def load_valid(self):
        """只返回 path 存在的记录"""
        all_data = await self.load_all()
        return [info for info in all_data if os.path.exists(info["path"])]

    async def save_all(self, gallery_data: list[dict]):
        """保存所有图库信息（Manager 会给完整列表）"""
        async with aiofiles.open(self.db_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(gallery_data, indent=4, ensure_ascii=False))
