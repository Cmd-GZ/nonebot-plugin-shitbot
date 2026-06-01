from __future__ import annotations

from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot

from ..command import BotCommand
from ..parser import BotArgParser

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandPerm(BotCommand):
    _name = "perm"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0)

        # === /perm check ===
        check = parser.add_subparser("check")
        check.set_rule(max=0)

        # === /perm list -t <user|group|entry> [--all] ===
        lst = parser.add_subparser("list")
        lst.set_rule(max=0)
        lst.add_opt(
            "-t", required=True, necessary=True, choice=["user", "group", "entry"]
        )
        lst.add_opt("--all")

        # === /perm info -U <user perm group name>... -G <group perm group name>... ===
        info = parser.add_subparser("info")
        info.set_rule(max=0)
        info.add_opt("-U", required=True, max_appeared=99)
        info.add_opt("-G", required=True, max_appeared=99)

        # === /perm create -U <user perm group name>... -G <group perm group name>... ===
        create = parser.add_subparser("create")
        create.set_rule(max=0)
        create.add_opt("-U", required=True, max_appeared=99)
        create.add_opt("-G", required=True, max_appeared=99)

        # === /perm delete -U <user perm group name>... -G <group perm group name>... ===
        delete = parser.add_subparser("delete")
        delete.set_rule(max=0)
        delete.add_opt("-U", required=True, max_appeared=99)
        delete.add_opt("-G", required=True, max_appeared=99)

        # === /perm add -U <user perm group name>... -G <group perm group name>... -u <user ID>... -g <group ID>... ===
        add = parser.add_subparser("add")
        add.set_rule(max=0)
        add.add_opt("-U", required=True, max_appeared=99)
        add.add_opt("-G", required=True, max_appeared=99)
        add.add_opt("-u", required=True, max_appeared=99)
        add.add_opt("-g", required=True, max_appeared=99)

        # === /perm remove -U <user perm group name>... -G <group perm group name>... -u <user ID>... -g <group ID>... ===
        remove = parser.add_subparser("remove")
        remove.set_rule(max=0)
        remove.add_opt("-U", required=True, max_appeared=99)
        remove.add_opt("-G", required=True, max_appeared=99)
        remove.add_opt("-u", required=True, max_appeared=99)
        remove.add_opt("-g", required=True, max_appeared=99)

        # === /perm entry -t <user|group> <subcommand> [选项] <entry name> ===
        entry = parser.add_subparser("entry")
        entry.set_rule(max=0)
        entry.add_opt("-t", required=True, necessary=True, choice=["user", "group"])

        # whitelist -s <on|off> <entry name>
        whitelist = entry.add_subparser("whitelist")
        whitelist.set_rule(min=1, max=1)
        whitelist.add_opt("-s", required=True, necessary=True, choice=["on", "off"])

        # whites -A <perm group name>... -R <perm group name>... <entry name>
        whites = entry.add_subparser("whites")
        whites.set_rule(min=1, max=1)
        whites.add_opt("-A", required=True, max_appeared=99)
        whites.add_opt("-R", required=True, max_appeared=99)

        # blacks -A <perm group name>... -R <perm group name>... <entry name>
        blacks = entry.add_subparser("blacks")
        blacks.set_rule(min=1, max=1)
        blacks.add_opt("-A", required=True, max_appeared=99)
        blacks.add_opt("-R", required=True, max_appeared=99)

        return parser
