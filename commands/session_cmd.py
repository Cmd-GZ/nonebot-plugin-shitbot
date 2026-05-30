from __future__ import annotations

import json
from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot, Message

from ..command import BotCommand
from ..parser import BotArgParser

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandSession(BotCommand):
    _name = "session"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0, need_subcmd=True)
        switch = parser.add_subparser("switch")
        info = parser.add_subparser("info")
        switch.set_rule(min=1, max=1, types=[int])
        info.set_rule(max=0)
        return parser

    async def run(self, args: Message):
        if self.session is None:
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
            await self.send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        subcmd = self._parser.subcmd

        if subcmd == "switch":
            if self._parser.subparsers[subcmd].value is None:
                return  # Also impossible
            pid = self._parser.subparsers[subcmd].value[0]

            if pid <= 0:
                tip = "错误：pid不合规\n"
                tip += "pid应大于0。"
                await self.send_msg(tip)
                self.unlock()
                return

            self.session.curpid = pid
            await self.send_msg(f"已将前台pid设为 {pid}")
            if len(self.session.commands.keys()) <= 1:
                await self.send_msg(
                    "警告：当前无其它命令正在运行，该设置会随着用户会话被释放而被重置。"
                )

        if subcmd == "info":
            commands = self.session.commands
            cmd_info = {pid: cmd.name for pid, cmd in commands.items()}
            tip = f"前台pid: {self.session.curpid}\n\n"
            tip += f"正在运行的命令: \n{json.dumps(cmd_info, indent=2, ensure_ascii=False)}"
            await self.send_msg(tip)

        self.unlock()
