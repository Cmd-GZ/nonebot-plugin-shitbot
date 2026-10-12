from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import random

from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger

from ..command import BotCommand
from ..parser import BotArgParser

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandRandpic(BotCommand):
    _name = "randpic"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._r18 = 0
        self._limit = 1
        self._keyword = ""
        self._data_pool: list[list[dict[str, Any]]] = []

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0)
        parser.add_opt("-r", required=True, choice=["off", "on", "only"], default=["off"])
        parser.add_opt("-n", required=True, type=int, default=[1])
        parser.add_opt("-k", required=True, type=str, default=[""])
        return parser

    async def get_pic_num(self) -> int:
        api = "https://api.manyacg.top/v1/artwork/list"
        payload: dict[str, Any] = {
            "r18": self._r18,
            "keyword": self._keyword,
            "page_size": 200,
        }
        headers = {"Content-Type": "application/json"}
        upper_bound = 1
        while True:
            payload["page"] = upper_bound
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api, headers=headers, json=payload)
            if response.status_code != 200 or not response.json().get("data"):
                if upper_bound == 1:
                    return 0
                break
            pool_length = len(self._data_pool)
            blank_slots = upper_bound - pool_length - 1
            for _ in range(blank_slots):
                self._data_pool.append([])
            self._data_pool.append(response.json().get("data", []))
            if len(response.json().get("data")) < 200:
                return 200 * (upper_bound - 1) + len(response.json().get("data"))
            upper_bound *= 2

        if len(self._data_pool) < upper_bound:
            blank_slots = upper_bound - len(self._data_pool)
            for _ in range(blank_slots):
                self._data_pool.append([])
        lower_bound = upper_bound // 2
        while lower_bound < upper_bound - 1:
            mid = (lower_bound + upper_bound) // 2
            payload["page"] = mid
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api, headers=headers, json=payload)
            if response.status_code != 200 or not response.json().get("data"):
                upper_bound = mid
                continue
            else:
                lower_bound = mid
            self._data_pool[mid - 1] = response.json().get("data", [])
            if len(response.json().get("data")) < 200:
                return 200 * (mid - 1) + len(response.json().get("data"))

        return 200 * lower_bound

    async def get_pics(self, limit: int, pic_num: int) -> list[dict[str, Any]]:
        if pic_num == 0:
            return []
        pics: list[dict[str, Any]] = []
        api = "https://api.manyacg.top/v1/artwork/list"
        payload: dict[str, Any] = {
            "r18": self._r18,
            "keyword": self._keyword,
            "page_size": 200,
        }
        headers = {"Content-Type": "application/json"}
        limit = min(limit, pic_num)
        random_indices = random.sample(range(pic_num), limit)
        if not self._data_pool:
            self._data_pool = [[] for _ in range((pic_num + 199) // 200)]
        for index in random_indices:
            page = index // 200
            offset = index % 200
            if not self._data_pool[page]:
                payload["page"] = page + 1
                async with httpx.AsyncClient() as client:
                    response = await client.post(api, headers=headers, json=payload)
                if response.status_code != 200:
                    logger.error(f"api调用失败, 状态码{response.status_code}")
                    continue
                self._data_pool[page] = response.json().get("data", [])
            if offset >= len(self._data_pool[page]):
                continue
            pics.append(self._data_pool[page][offset])

        return pics

    async def send_pics(self, pics: list[dict[str, Any]]):
        if len(pics) < self._limit:
            await self.send_msg(f"未找到指定数量的图片，仅找到 {len(pics)} 张")
        for pic in pics:
            title = pic["title"]
            source = pic["source_url"]
            artist = pic["artist"]["name"]
            img_urls = [img_url["regular"] for img_url in pic["pictures"]]
            text = f"标题: {title}\n作者: {artist}\n来源: {source}\n"
            msg = Message()
            msg.append(MessageSegment("text", {"text": text}))
            for img_url in img_urls:
                seg = MessageSegment("image", {"url": img_url})
                seg.data["summary"] = "我的新自拍喵[图片]"
                msg.append(seg)
            try:
                await self.send_msg(msg)
                logger.info("发送图片成功")
            except Exception as e:
                logger.error(f"发送图片失败: {e}")
                text += f"\n图片发送失败, 大概率被河蟹了, 请尝试私聊使用该命令\n{e}"
                await self.send_msg(text)

    async def run(self, args: Message):
        if not self.session:
            return

        new_argv = args.extract_plain_text().strip().split()
        if not await self._legal_case(new_argv):
            if self._argv is None:
                self.unlock()
            return

        if not await self._guard_state():
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        r = self._parser.opts_value["-r"][0]
        n = self._parser.opts_value["-n"][0]

        self._limit = max(n, 1)
        self._limit = min(n, 10)

        if not self._check_perm("multisetu"):
            self._limit = 1

        if not self._check_perm("randpic"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        if (r == "on" or r == "only") and not self._check_perm("nsfw"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        if r == "on":
            self._r18 = 2
        elif r == "only":
            self._r18 = 1

        self._keyword = self._parser.opts_value["-k"][0]

        api = "https://api.manyacg.top/v1/artwork/list"
        if self._keyword.replace(" ", "").replace(",", "").replace("|", "") == "":
            api = "https://api.manyacg.top/v1/artwork/random"
            payload: dict[str, Any] = {
                "r18": self._r18,
                "limit": self._limit,
            }
            headers = {"Content-Type": "application/json"}
            async with httpx.AsyncClient() as client:
                response = await client.post(api, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error(f"api调用失败, 状态码{response.status_code}")
                self.unlock()
                return

            data = response.json()
            pics = data.get("data", [])

            await self.send_pics(pics)
            self.unlock()
            return

        pic_num = await self.get_pic_num()
        pics = await self.get_pics(self._limit, pic_num)
        await self.send_pics(pics)
        self.unlock()


#        for i in range(num):
#            try:
#                msg = Message(MessageSegment("image", {"url": api}))
#                msg[0].data["summary"] = "我的新自拍喵[图片]"
#                await self.send_msg(msg)
#                logger.info("发送图片成功")
#            except Exception as e:
#                logger.error(f"发送图片失败: {e}")
#                await self.send_msg(f"图片发送失败：{e}")
