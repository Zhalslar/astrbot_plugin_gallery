import aiohttp
import zipfile
import os
import shutil
from astrbot import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent

def get_dirs(path: str) ->  list[str]:
    """
    获取指定目录下的所有子目录路径（不包括文件）
    """
    directories = []
    with os.scandir(path) as entries:
        for entry in entries:
            if entry.is_dir():
                directories.append(entry.path)
    return directories


async def download_file(url: str) -> bytes | None:
    """下载图片"""
    url = url.replace("https://", "http://")
    try:
        async with aiohttp.ClientSession() as client:
            response = await client.get(url)
            img_bytes = await response.read()
            return img_bytes
    except Exception as e:
        logger.error(f"图片下载失败: {e}")

async def get_nickname(event: AstrMessageEvent, target_id: str):
    """从消息平台获取参数"""
    if event.get_platform_name() == "aiocqhttp":
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        assert isinstance(event, AiocqhttpMessageEvent)
        client = event.bot
        user_info = await client.get_stranger_info(user_id=int(target_id))
        nickname = user_info.get("nickname")
        return nickname
    # TODO 适配更多消息平台
    return f"{target_id}"


def unzip_file(zip_path: str, folder_path: str) -> bool:
    """解压压缩包，成功返回True，失败返回False"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(folder_path)
        return True
    except Exception as e:
        logger.error(f"解压文件 {zip_path} 失败: {e}")
        return False


def zip_folder(folder_path: str, zip_path: str) -> bool:
    """压缩文件夹，成功返回True，失败返回False"""
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(
                        file_path, arcname=os.path.relpath(file_path, start=folder_path)
                    )
        return True
    except Exception as e:
        logger.error(f"压缩文件夹 {folder_path} 失败: {e}")
        return False


def move_files_up(directory):
    """
    如果目录下只有一个子文件夹，移动其中的所有文件和子文件夹到上一级目录，并删除该子文件夹。
    递归检查直到不满足条件。
    保持子文件夹内的文件结构。
    """
    while True:
        # 获取目录下所有的子目录和文件
        entries = os.listdir(directory)
        subfolders = [
            entry for entry in entries if os.path.isdir(os.path.join(directory, entry))
        ]

        # 如果只有一个子文件夹
        if len(subfolders) == 1:
            subfolder_path = os.path.join(directory, subfolders[0])

            # 遍历子文件夹中的所有内容并移动到上一级目录
            for root, dirs, files in os.walk(subfolder_path, topdown=False):
                # 移动文件
                for file in files:
                    file_path = os.path.join(root, file)
                    shutil.move(file_path, os.path.join(directory, file))

                # 移动子文件夹
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    shutil.move(dir_path, os.path.join(directory, dir))

            # 删除子文件夹
            shutil.rmtree(subfolder_path)

            # 继续检查上级目录
            continue

        # 如果不是只有一个子文件夹，退出循环
        break

