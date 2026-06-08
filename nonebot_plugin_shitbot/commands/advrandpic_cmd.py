from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger

from ..command import BotCommand
from ..parser import BotArgParser

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandAdvrandpic(BotCommand):
    _name = "advrandpic"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._r18 = 0
        self._num = 1
        self._tag = None
        self._size = "regular"

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0)
        parser.add_opt(
            "-r", required=True, choice=["off", "on", "only"], default=["off"]
        )
        parser.add_opt(
            "-s", required=True, choice=["original", "regular"], default=["regular"]
        )
        parser.add_opt("-t", required=True)
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

        r18 = self._parser.opts_value["-r"][0]

        if r18 == "off":
            self._r18 = 0
        if r18 == "on":
            self._r18 = 2
        if r18 == "only":
            self._r18 = 1

        tags = self._parser.opts_value["-t"]
        if len(tags) > 0:
            self._tag = tags[0].split("&")

        self._num = self._parser.opts_value["-n"][0]
        self._num = max(self._num, 1)
        self._num = min(self._num, 10)
        if not self._check_perm("multisetu"):
            self._num = 1

        self._size = self._parser.opts_value["-s"][0]

        if not self._check_perm("advrandpic"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        if self._r18 and not self._check_perm("nsfw"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        api = "https://api.lolicon.app/setu/v2"
        payload: dict[str, Any] = {
            "r18": self._r18,
            "num": self._num,
            "size": self._size,
        }
        if self._tag is not None:
            payload["tag"] = self._tag
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient() as client:
            response = await client.post(api, headers=headers, json=payload)
        if response.status_code != 200:
            logger.error(f"api调用失败, 状态码{response.status_code}")
            self.unlock()
            return

        data = response.json()

        if len(data["data"]) < self._num:
            await self.send_msg(f"未找到指定数量的图片，仅找到 {len(data['data'])} 张")

        for pic in data["data"]:
            pid = str(pic["pid"])
            title = pic["title"]
            author = pic["author"]
            url = pic["urls"][self._size]
            text = f"标题: {title}\n作者: {author}\nPID:  {pid}"
            try:
                msg = Message(
                    [
                        MessageSegment("text", {"text": text}),
                        MessageSegment("image", {"url": url}),
                    ]
                )
                msg[0].data["summary"] = "我的新自拍喵[图片]"
                await self.send_msg(msg)
                logger.info("发送图片成功")
            except Exception as e:
                logger.error(f"发送图片失败: {e}")
                text += f"\n图片发送失败, 大概率被河蟹了, 请尝试私聊使用该命令\n{e}"
                await self.send_msg(text)

        self.unlock()
