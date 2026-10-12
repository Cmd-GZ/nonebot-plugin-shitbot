from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

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

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0)
        parser.add_opt("-r", required=True, choice=["off", "on", "only"], default=["off"])
        parser.add_opt("-n", required=True, type=int, default=[1])
        return parser

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

        for pic in data["data"]:
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



#        for i in range(num):
#            try:
#                msg = Message(MessageSegment("image", {"url": api}))
#                msg[0].data["summary"] = "我的新自拍喵[图片]"
#                await self.send_msg(msg)
#                logger.info("发送图片成功")
#            except Exception as e:
#                logger.error(f"发送图片失败: {e}")
#                await self.send_msg(f"图片发送失败：{e}")
        self.unlock()
