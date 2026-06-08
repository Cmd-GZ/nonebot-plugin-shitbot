from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot, Message

from ..command import BotCommand
from ..parser import BotArgParser
from .md2pic_cmd import BotCommandMd2pic

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandHelp(BotCommand):
    _name = "help"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.add_subparser("help")
        parser.add_subparser("session")
        parser.add_subparser("perm")
        parser.add_subparser("convert")
        parser.add_subparser("randpic")
        parser.add_subparser("shitpost")
        parser.add_subparser("advrandpic")
        parser.add_subparser("md2pic")
        parser.add_subparser("pixiv")
        return parser

    async def run(self, args: Message):
        if not self.session:
            return
        new_argv = args.extract_plain_text().strip().split()
        # I know it's impossible to be illegal. Just for formalism :)
        if not await self._legal_case(new_argv):
            if self._argv is None:
                self.unlock()
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)
        subcmd = self._parser.subcmd

        if not self._check_perm("help"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        help_dir = Path(__file__).resolve().parent.parent / "docs" / "help"
        tip = "错误: 帮助文档目录不存在"
        if help_dir.exists():
            tip = "错误: 帮助文档 index.md 不存在"
        help_path = help_dir / "index.md"
        if help_path.exists():
            tip = help_path.read_text(encoding="utf-8")
        if subcmd in (
            "help",
            "session",
            "perm",
            "convert",
            "randpic",
            "shitpost",
            "advrandpic",
            "md2pic",
            "pixiv",
        ):
            tip = f"错误: 帮助文档 {subcmd}.md 不存在"
            help_path = help_dir / f"{subcmd}.md"
            if help_path.exists():
                tip = help_path.read_text(encoding="utf-8")

        tip = re.sub(
            r"!\[([^\]]*)\]\((?!https?://|/)([^)]+)\)",
            lambda m: f"![{m.group(1)}]({(help_dir / m.group(2)).resolve()})",
            tip,
        )

        _pid = -1
        pids = self.session.commands.keys()
        while _pid in pids:
            _pid -= 1
        md2pic = BotCommandMd2pic.make(self.bot, self.session, _pid=_pid)
        tip = "-c\n" + tip
        msg = Message(tip)
        await md2pic.run(msg)  # type: ignore
        self.unlock()
