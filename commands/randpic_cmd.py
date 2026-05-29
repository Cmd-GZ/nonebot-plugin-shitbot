from __future__ import annotations

from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger

from ..command import BotCommand
from ..config import config
from ..parser import BotArgParser

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandRandpic(BotCommand):
    _name = "randpic"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0)
        parser.add_opt("-r", required=True, choice=["off", "on"], default=["off"])
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
            or self._parser.opts_value["-n"] is None
        ):
            return  # It's impossible, just for type checking
        r18 = self._parser.opts_value["-r"][0]
        num = self._parser.opts_value["-n"][0]

        num = max(num, 1)
        num = min(num, 10)

        if self.session.group_id != "private":
            num = 1

        if r18 == "on" and self.session.group_id != "private":
            tip = "该功能只能在私聊中使用"
            await self._send_msg(tip)
            self.unlock()
            return

        if self.session.group_id not in config.whitelist_groups_setu:
            self.unlock()
            return

        api = "https://manyacg.top/setu"
        if r18 == "on":
            if self.session.user_id not in config.whitelist_users_setu:
                self.unlock()
                return
            api = "https://manyacg.top/sese"
        for i in range(num):
            try:
                msg = Message(MessageSegment("image", {"url": api}))
                msg[0].data["summary"] = "我的新自拍喵[图片]"
                await self._send_msg(msg)
                logger.info("发送图片成功")
            except Exception as e:
                logger.error(f"发送图片失败: {e}")
                await self._send_msg(f"图片发送失败：{e}")
        self.unlock()
