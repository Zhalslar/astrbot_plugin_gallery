# utils/zip_utils.py

import os
import shutil
import zipfile

from astrbot.api import logger


class ZipUtils:
    @staticmethod
    def unzip_file(zip_path: str, folder_path: str) -> bool:
        """解压压缩包，成功返回 True，失败返回 False"""
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(folder_path)
            return True
        except Exception as e:
            logger.error(f"解压文件 {zip_path} 失败: {e}")
            return False

    @staticmethod
    def zip_folder(folder_path: str, zip_path: str) -> bool:
        """压缩文件夹，成功返回 True，失败返回 False"""
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        zipf.write(
                            file_path,
                            arcname=os.path.relpath(file_path, start=folder_path),
                        )
            return True
        except Exception as e:
            logger.error(f"压缩文件夹 {folder_path} 失败: {e}")
            return False

    @staticmethod
    def move_files_up(directory: str):
        """
        保持原逻辑：
        - 如果目录下只有一个子文件夹
        - 把其中所有内容提升到当前目录
        - 并删除子文件夹
        - 递归直到不再满足条件
        """
        while True:
            entries = os.listdir(directory)
            subfolders = [
                entry
                for entry in entries
                if os.path.isdir(os.path.join(directory, entry))
            ]

            if len(subfolders) == 1:
                subfolder_path = os.path.join(directory, subfolders[0])

                for root, dirs, files in os.walk(subfolder_path, topdown=False):
                    # 移动文件
                    for file in files:
                        file_path = os.path.join(root, file)
                        shutil.move(file_path, os.path.join(directory, file))

                    # 移动子目录
                    for dir in dirs:
                        dir_path = os.path.join(root, dir)
                        shutil.move(dir_path, os.path.join(directory, dir))

                shutil.rmtree(subfolder_path)
                continue

            break

    @staticmethod
    def unzip_to_folder(zip_file_path: str, root_dir: str) -> str | None:
        """
        自动生成解压文件夹路径、检查冲突、解压并自动 move_files_up。
        成功返回解压后的文件夹路径，失败返回 None。
        """
        folder_name = os.path.basename(zip_file_path).rsplit(".", 1)[0]
        folder_path = os.path.join(root_dir, folder_name)

        # 判断是否冲突
        if os.path.exists(folder_path):
            logger.warning(f"已存在同名文件夹【{folder_name}】，跳过：{zip_file_path}")
            return None

        # 解压
        if not ZipUtils.unzip_file(zip_file_path, folder_path):
            return None

        # 自动展开目录层级
        ZipUtils.move_files_up(folder_path)

        return folder_path


    @staticmethod
    def extract_all_zips(root_dir: str):
        """
        扫描 root_dir 下所有 zip，解压、自动展开目录、删除原 zip。
        返回所有成功解压后的文件夹路径列表。
        """
        extracted_folders = []

        for entry in os.scandir(root_dir):
            if not (entry.is_file() and entry.name.lower().endswith(".zip")):
                continue

            # 解压到文件夹
            folder_path = ZipUtils.unzip_to_folder(entry.path, root_dir)
            if folder_path is None:
                continue  # 冲突或失败

            # 删除 zip
            os.remove(entry.path)

            extracted_folders.append(folder_path)

        return extracted_folders
