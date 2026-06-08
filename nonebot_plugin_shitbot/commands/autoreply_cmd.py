from __future__ import annotations

from nonebot.adapters.onebot.v11 import Bot, Message

from ..command import BotCommand
from ..parser import BotArgParser
from ..session import BotSession
from .autoreply_main_cmd import BotCommandAutoReplyMain


class BotCommandAutoreply(BotCommand):
    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0, need_subcmd=True)
        start = parser.add_subparser("start")
        stop = parser.add_subparser("stop")
        start.set_rule(max=0)
        stop.set_rule(max=0)
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
        subcmd = self._parser.subcmd

        if not self._check_perm("autoreplymanager"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        if subcmd == "start":
            autoreply_session = BotSession.make("public", "autoreply")
            main_command = BotCommandAutoReplyMain.make(
                self.bot, autoreply_session, _pid=autoreply_session.curpid
            )
            if main_command is None:
                await self.send_msg("警告: 自动回复正在运行中")
            await self.send_msg("自动回复已开启")
            self.unlock()

        elif subcmd == "stop":

            async def _exe():
                autoreply_session = BotSession.get_obj("public", "autoreply")
                if autoreply_session is None:
                    await self.send_msg("警告: 自动回复未开启")
                    return
                main_command = autoreply_session.commands.get(autoreply_session.curpid)
                if main_command is None:
                    await self.send_msg("警告: 自动回复未开启")
                    return
                main_command.unlock()

            await _exe()
            await self.send_msg("自动回复已关闭")
            self.unlock()
