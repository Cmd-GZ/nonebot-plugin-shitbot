from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger

from ..command import BotCommand
from ..config import config
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

        if self._argv is not None:
            command = self.session.commands.get(self._pid)
            if not command:
                return
            tip = "错误：会话被占用\n"
            tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)
        if (
            self._parser.opts_value["-r"] is None
            or self._parser.opts_value["-s"] is None
            or self._parser.opts_value["-n"] is None
        ):  # It's impossible
            return

        r18 = self._parser.opts_value["-r"][0]
        if r18 != "off" and self.session.group_id != "private":
            tip = "该功能只能在私聊中使用"
            await self._send_msg(tip)
            self.unlock()
            return
        if r18 == "off":
            self._r18 = 0
        if r18 == "on":
            self._r18 = 2
        if r18 == "only":
            self._r18 = 1

        tags = self._parser.opts_value["-t"]
        if tags is not None:
            self._tag = tags[0].split("&")

        self._num = self._parser.opts_value["-n"][0]
        self._num = max(self._num, 1)
        self._num = min(self._num, 10)
        if self.session.group_id != "private":
            self._num = 1

        self._size = self._parser.opts_value["-s"][0]

        if self.session.group_id not in config.whitelist_groups_setu:
            self.unlock()
            return

        if self._r18 and self.session.user_id not in config.whitelist_users_setu:
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
            logger.error(f"api调用失败，状态码{response.status_code}")
            self.unlock()
            return

        data = response.json()

        if len(data["data"]) < self._num:
            await self._send_msg(f"未找到指定数量的图片，仅找到 {len(data['data'])} 张")

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
                await self._send_msg(msg)
                logger.info("发送图片成功")
            except Exception as e:
                logger.error(f"发送图片失败: {e}")
                text += f"\n图片发送失败, 大概率被河蟹了, 请尝试私聊使用该命令\n{e}"
                await self._send_msg(text)

        self.unlock()
