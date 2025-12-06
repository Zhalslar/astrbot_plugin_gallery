import json
import random
import re
import time

import astrbot.core.message.components as Comp
from astrbot.api import logger
from astrbot.core import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.provider import Provider
from astrbot.core.star.context import Context
from data.plugins.astrbot_plugin_gallery.utils import get_image

from ..core import GalleryManager, RelevanceBM25
from ..utils import download_file


class GalleryAuto:
    def __init__(
        self, context: Context, config: AstrBotConfig, manager: GalleryManager
    ):
        self.context = context
        self.conf = config
        self.manager = manager
        self.matcher = RelevanceBM25()

        self.last_collect_time: int = 0

    # --------------自动收集、打标-------------------

    async def get_llm_tags(
        self, image_url: str, galleries_names: list[str]
    ) -> str | None:
        """调用 LLM 获取格式化标签文本"""
        provider = (
            self.context.get_provider_by_id(self.conf["auto_collect"]["provider_id"])
            or self.context.get_using_provider()
        )

        if not isinstance(provider, Provider):
            return None

        # —— 构造更稳定的提示词 ——
        system_prompt = (
            "你是用于图片自动分类的助手，请严格按照以下规则工作：\n"
            "\n"
            "1. 只允许输出 **完整合法 JSON**，禁止输出解释或额外文本。\n"
            f"2. 当前已有图库列表：{galleries_names}\n"
            "\n"
            "3. 判断图片是否属于已有图库：\n"
            "   - 如果属于：输出：\n"
            '     {"gallery": "<已有图库名>", "tags": []}\n'
            "   - 如果不属于：输出：\n"
            '     {"gallery": "<建议的新图库名>", "tags": ["tag1", "tag2", "tag3"]}\n'
            "\n"
            "4. 要求：\n"
            "   - gallery 必须为字符串\n"
            "   - tags 必须为字符串数组\n"
            "   - 必须且只能返回一个 JSON 对象\n"
        )
        try:
            logger.debug(system_prompt)
            llm_response = await provider.text_chat(
                system_prompt=system_prompt,
                prompt="这是要进行归类的图片",
                image_urls=[image_url],
            )
            text = llm_response.completion_text
            logger.debug(text)
            return text

        except Exception as e:
            logger.error(f"LLM 调用失败：{e}")
            return None

    @staticmethod
    def parse_llm_tags(text: str) -> tuple[str | None, list[str]]:
        """
        返回格式：(gallery_name, tags)
        gallery_name: str | None
        tags: list[str]
        """

        gallery_name = None
        tags: list[str] = []

        if not text:
            return gallery_name, tags

        # 1) 尝试直接 JSON
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                gallery_name = str(data.get("gallery")) if data.get("gallery") else None
                if isinstance(data.get("tags"), list):
                    tags = [str(t) for t in data["tags"]]
                return gallery_name, tags
        except Exception:
            pass

        # 2) 正则提取 JSON 块 { ... }
        match = re.search(r"\{[\s\S]*?\}", text)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    gallery_name = (
                        str(data.get("gallery")) if data.get("gallery") else None
                    )
                    if isinstance(data.get("tags"), list):
                        tags = [str(t) for t in data["tags"]]
                    return gallery_name, tags
            except Exception:
                pass

        logger.warning(f"无法解析 LLM 标签输出：{text!r}")
        return gallery_name, tags

    async def collect_image(self, event: AstrMessageEvent):
        """自动收集、打标图片"""
        conf = self.conf["auto_collect"]
        # 开关
        if not conf["enable_collect"]:
            return
        # 群聊白名单
        if conf["whitelist"] and event.get_group_id() not in conf["whitelist"]:
            return
        # 冷却时间
        if (
            conf["collect_cd"] > 0
            and int(time.time()) - self.last_collect_time < conf["collect_cd"]
        ):
            return
        # 获取图片URL
        image_url = await get_image(event, reply=False, get_url=True)
        if not isinstance(image_url, str):
            return
        # 打标
        galleries_names = self.manager.get_all_galleries_names()
        llm_text = await self.get_llm_tags(image_url, galleries_names)
        if not llm_text:
            return
        gallery_name, tags = self.parse_llm_tags(llm_text)
        if not gallery_name:
            return
        gallery = self.manager.get_gallery(gallery_name)
        if not gallery:
            gallery = await self.manager.create_gallery(
                gallery_name,
                creator_id=event.get_sender_id(),
                creator_name=event.get_sender_name(),
            )
            await self.manager.set_tags(name=gallery.name, tags=tags)
        # 收集图片
        if image_bytes := await download_file(image_url):
            succ, result = gallery.add_image(
                image_bytes, author=event.get_sender_name()
            )
            if succ:
                logger.info(f"自动收集图片：{result}")

    # --------------自动匹配、发图-------------------

    async def match_user_msg(self, event: AstrMessageEvent):
        """给用户发送的消息匹配图片"""
        text = event.message_str
        if not text:
            return
        conf = self.conf["auto_match"]
        if random.random() < conf["user_prob"]:
            for gallery in self.manager.get_all_gallery():
                score = self.matcher.calc(tags=gallery.tags, msg=text)
                #print(f"{gallery.tags}: {score}")
                if score > conf["user_threshold"]:
                    succ, image = gallery.get_random_image()
                    if succ:
                        await event.send(event.image_result(image))  # type: ignore
                    break

    async def match_llm_msg(self, event: AstrMessageEvent, resp: LLMResponse):
        """给LLM响应的消息匹配图片"""
        conf = self.conf["auto_match"]
        if random.random() < conf["llm_prob"]:
            chain = resp.result_chain.chain if resp.result_chain else None
            if not chain:
                return
            text = (
                chain[0].text
                if len(chain) == 1 and isinstance(chain[0], Comp.Plain)
                else ""
            )
            for gallery in self.manager.get_all_gallery():
                score = self.matcher.calc(tags=gallery.tags, msg=text)
                if score > conf["llm_threshold"]:
                    succ, image = gallery.get_random_image()
                    if succ:
                        await event.send(event.image_result(image))  # type: ignore
                break
