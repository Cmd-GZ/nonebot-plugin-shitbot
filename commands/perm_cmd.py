from __future__ import annotations

from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot, Message

from ..command import BotCommand
from ..parser import BotArgParser
from ..permissions import permissions

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandPerm(BotCommand):
    _name = "perm"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._t: str = ""
        self._all: bool = False
        self._U: list[str] = []
        self._G: list[str] = []
        self._E: list[str] = []
        self._u: list[str] = []
        self._g: list[str] = []
        self._s: bool = False
        self._A: list[str] = []
        self._R: list[str] = []
        self._entries: list[str] = []

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0, need_subcmd=True)

        # === /perm check ===
        check = parser.add_subparser("check")
        check.set_rule(max=0)

        # === /perm list -t <user|group|entry> [--all] ===
        lst = parser.add_subparser("list")
        lst.set_rule(max=0)
        lst.add_opt(
            "-t", required=True, necessary=True, choice=["user", "group", "entry"]
        )
        lst.add_opt("--all", default=[0])

        # === /perm info -U <user perm group name>... -G <group perm group name>... -E <entry name>... ===
        info = parser.add_subparser("info")
        info.set_rule(max=0)
        info.add_opt("-U", required=True, max_appeared=None)
        info.add_opt("-G", required=True, max_appeared=None)
        info.add_opt("-E", required=True, max_appeared=None)

        # === /perm create -U <user perm group name>... -G <group perm group name>... ===
        create = parser.add_subparser("create")
        create.set_rule(max=0)
        create.add_opt("-U", required=True, max_appeared=None)
        create.add_opt("-G", required=True, max_appeared=None)

        # === /perm delete -U <user perm group name>... -G <group perm group name>... ===
        delete = parser.add_subparser("delete")
        delete.set_rule(max=0)
        delete.add_opt("-U", required=True, max_appeared=None)
        delete.add_opt("-G", required=True, max_appeared=None)

        # === /perm add -U <user perm group name>... -G <group perm group name>... -u <user ID>... -g <group ID>... ===
        add = parser.add_subparser("add")
        add.set_rule(max=0)
        add.add_opt("-U", required=True, max_appeared=None)
        add.add_opt("-G", required=True, max_appeared=None)
        add.add_opt("-u", required=True, max_appeared=None)
        add.add_opt("-g", required=True, max_appeared=None)

        # === /perm remove -U <user perm group name>... -G <group perm group name>... -u <user ID>... -g <group ID>... ===
        remove = parser.add_subparser("remove")
        remove.set_rule(max=0)
        remove.add_opt("-U", required=True, max_appeared=None)
        remove.add_opt("-G", required=True, max_appeared=None)
        remove.add_opt("-u", required=True, max_appeared=None)
        remove.add_opt("-g", required=True, max_appeared=None)

        # === /perm entry -t <user|group> <subcommand> [options] <entry name 1> [entry name 2] ... ===
        entry = parser.add_subparser("entry")
        entry.set_rule(max=0)
        entry.add_opt("-t", required=True, necessary=True, choice=["user", "group"])

        # whitelist -s <on|off> <entry name>
        whitelist = entry.add_subparser("whitelist")
        whitelist.set_rule(min=1)
        whitelist.add_opt("-s", required=True, necessary=True, choice=["on", "off"])

        # whites -A <perm group name>... -R <perm group name>... <entry name 1> [entry name 2] ...
        whites = entry.add_subparser("whites")
        whites.set_rule(min=1)
        whites.add_opt("-A", required=True, max_appeared=None)
        whites.add_opt("-R", required=True, max_appeared=None)

        # blacks -A <perm group name>... -R <perm group name>... <entry name 1> [entry name 2] ...
        blacks = entry.add_subparser("blacks")
        blacks.set_rule(min=1)
        blacks.add_opt("-A", required=True, max_appeared=None)
        blacks.add_opt("-R", required=True, max_appeared=None)

        return parser

    async def _check(self):
        if self.session is None:
            return
        keys = permissions.entries.keys()
        tip = "权限状态概览:\n"
        tip += f"用户ID: {self.session.user_id}, 群组ID: {self.session.group_id}\n"
        for key in keys:
            des = permissions.entries[key]["description"]
            enable = permissions.check_permission(
                key, self.session.group_id, self.session.user_id
            )
            if key == "permmanager":
                enable = enable or permissions.owners_check_permission(
                    key, self.session.group_id, self.session.user_id
                )
            tip += f"{des}: {enable}\n"
        await self.send_msg(tip)

    async def _list(self):
        if self.session is None:
            return
        keys = []
        tip = ""
        dic = {}
        if self._t == "users":
            keys = permissions.users.keys()
            dic = permissions.users
            tip = "用户权限组列表:\n"
        if self._t == "groups":
            keys = permissions.groups.keys()
            dic = permissions.groups
            tip = "群组权限组列表:\n"
        if self._t == "entries":
            keys = permissions.entries.keys()
            dic = permissions.entries
            tip = "权限项列表:\n"

        for key in keys:
            tip += f"{key}"
            if self._all:
                tip += f":\n{dic[key]}"
            tip += "\n"
        await self.send_msg(tip)

    async def _info(self):
        if self.session is None:
            return
        tip = "用户权限组信息:\n"
        for key in self._U:
            tip += f"{key}:\n{permissions.users.get(key, '未创建')}\n"
        tip += "群组权限组信息:\n"
        for key in self._G:
            tip += f"{key}:\n{permissions.groups.get(key, '未创建')}\n"
        tip += "权限项信息:\n"
        for key in self._E:
            tip += f"{key}:\n{permissions.entries.get(key, '未创建')}\n"
        await self.send_msg(tip)

    async def _create(self):
        if self.session is None:
            return
        try:
            for key in self._U:
                if key in permissions.users:
                    await self.send_msg(f"警告: 用户权限组 {key} 已存在")
                    continue
                permissions.users[key] = []
            for key in self._G:
                if key in permissions.groups:
                    await self.send_msg(f"警告: 群组权限组 {key} 已存在")
                    continue
                permissions.groups[key] = []
            if len(self._U) > 0:
                permissions.update_users()
            if len(self._G) > 0:
                permissions.update_groups()
            await self.send_msg("创建成功")
        except Exception as e:
            await self.send_msg(f"创建失败：{e}")

    async def _delete(self):
        if self.session is None:
            return
        try:
            for key in self._U:
                temp = permissions.users.pop(key, None)
                if temp is None:
                    await self.send_msg(f"警告: 用户权限组 {key} 不存在")
            for key in self._G:
                temp = permissions.groups.pop(key, None)
                if temp is None:
                    await self.send_msg(f"警告: 群组权限组 {key} 不存在")
            if len(self._U) > 0:
                permissions.update_users()
            if len(self._G) > 0:
                permissions.update_groups()
            await self.send_msg("删除成功")
        except Exception as e:
            await self.send_msg(f"删除失败：{e}")

    async def _add(self):
        if self.session is None:
            return
        try:
            length = min(len(self._U), len(self._u))
            is_edited = False
            for i in range(length):
                users = permissions.users.get(self._U[i])
                if users is None:
                    await self.send_msg(f"警告: 用户权限组 {self._U[i]} 不存在")
                    continue
                if self._u[i] in users:
                    await self.send_msg(
                        f"警告: 用户权限组 {self._U[i]} 中已存在用户 {self._u[i]}"
                    )
                    continue
                users.append(self._u[i])
                is_edited = True
            if is_edited:
                permissions.update_users()

            length = min(len(self._G), len(self._g))
            is_edited = False
            for i in range(length):
                groups = permissions.groups.get(self._G[i])
                if groups is None:
                    await self.send_msg(f"警告: 群组权限组 {self._G[i]} 不存在")
                    continue
                if self._g[i] in groups:
                    await self.send_msg(
                        f"警告: 群组权限组 {self._G[i]} 中已存在群组 {self._g[i]}"
                    )
                    continue
                groups.append(self._g[i])
                is_edited = True
            if is_edited:
                permissions.update_groups()

            await self.send_msg("添加成功")
        except Exception as e:
            await self.send_msg(f"添加失败：{e}")

    async def _remove(self):
        if self.session is None:
            return
        try:
            length = min(len(self._U), len(self._u))
            is_edited = False
            for i in range(length):
                users = permissions.users.get(self._U[i])
                if users is None:
                    await self.send_msg(f"警告: 用户权限组 {self._U[i]} 不存在")
                    continue
                if self._u[i] not in users:
                    await self.send_msg(
                        f"警告: 用户权限组 {self._U[i]} 中不存在用户 {self._u[i]}"
                    )
                    continue
                users.remove(self._u[i])
                is_edited = True
            if is_edited:
                permissions.update_users()

            length = min(len(self._G), len(self._g))
            is_edited = False
            for i in range(length):
                groups = permissions.groups.get(self._G[i])
                if groups is None:
                    await self.send_msg(f"警告: 群组权限组 {self._G[i]} 不存在")
                    continue
                if self._g[i] not in groups:
                    await self.send_msg(
                        f"警告: 群组权限组 {self._G[i]} 中不存在群组 {self._g[i]}"
                    )
                    continue
                groups.remove(self._g[i])
                is_edited = True
            if is_edited:
                permissions.update_groups()

            await self.send_msg("移除成功")
        except Exception as e:
            await self.send_msg(f"移除失败：{e}")

    async def _whitelist(self):
        if self.session is None:
            return
        try:
            is_edited = False
            for key in self._entries:
                if key not in permissions.entries:
                    await self.send_msg(f"警告: 权限项 {key} 不存在")
                    continue
                permissions.entries[key][self._t]["is_white"] = self._s
                is_edited = True
            if is_edited:
                permissions.update_entries()
            await self.send_msg("设置成功")
        except Exception as e:
            await self.send_msg(f"设置失败：{e}")

    async def _whites(self):
        if self.session is None:
            return
        try:
            is_edited = False
            for key in self._entries:
                if key not in permissions.entries:
                    await self.send_msg(f"警告: 权限项 {key} 不存在")
                    continue
                whites = permissions.entries[key][self._t]["whites"]
                for perms in self._A:
                    if perms in whites:
                        await self.send_msg(
                            f"警告: 权限项 {key} 的白名单中已存在权限组 {perms}"
                        )
                        continue
                    whites.append(perms)
                    is_edited = True
                for perms in self._R:
                    if perms not in whites:
                        await self.send_msg(
                            f"警告: 权限项 {key} 的白名单中不存在权限组 {perms}"
                        )
                        continue
                    whites.remove(perms)
                    is_edited = True
            if is_edited:
                permissions.update_entries()
            await self.send_msg("设置成功")
        except Exception as e:
            await self.send_msg(f"设置失败：{e}")

    async def _blacks(self):
        if self.session is None:
            return
        try:
            is_edited = False
            for key in self._entries:
                if key not in permissions.entries:
                    await self.send_msg(f"警告: 权限项 {key} 不存在")
                    continue
                blacks = permissions.entries[key][self._t]["blacks"]
                for perms in self._A:
                    if perms in blacks:
                        await self.send_msg(
                            f"警告: 权限项 {key} 的黑名单中已存在权限组 {perms}"
                        )
                        continue
                    blacks.append(perms)
                    is_edited = True
                for perms in self._R:
                    if perms not in blacks:
                        await self.send_msg(
                            f"警告: 权限项 {key} 的黑名单中不存在权限组 {perms}"
                        )
                        continue
                    blacks.remove(perms)
                    is_edited = True
            if is_edited:
                permissions.update_entries()
            await self.send_msg("设置成功")
        except Exception as e:
            await self.send_msg(f"设置失败：{e}")

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
            await self.send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        subcmd = self._parser.subcmd
        if subcmd is None:
            self.unlock()
            return
        subsubcmd = None

        nomanager = not permissions.owners_check_permission(
            "permmanager", self.session.group_id, self.session.user_id
        ) and not self._check_perm("permmanager")

        if (nomanager and subcmd != "check") or (
            subcmd == "check" and not self._check_perm("perm") and nomanager
        ):
            await self.send_msg("权限不足")
            self.unlock()
            return

        subparser = self._parser.subparsers[subcmd]
        _t = subparser._opts_value.get("-t", [self._t])[0]
        if _t == "user" or _t == "group":
            self._t = _t + "s"
        if _t == "entry":
            self._t = "entries"

        if subparser._opts_value.get("--all", [0])[0]:
            self._all = True
        self._U = subparser._opts_value.get("-U", self._U)
        self._G = subparser._opts_value.get("-G", self._G)
        self._E = subparser._opts_value.get("-E", self._E)
        self._u = subparser._opts_value.get("-u", self._u)
        self._g = subparser._opts_value.get("-g", self._g)

        subsubcmd = None
        if subcmd == "entry":
            subsubcmd = self._parser.subparsers[subcmd].subcmd
            if subsubcmd is None:
                self.unlock()
                return
            subsubparser = self._parser.subparsers[subcmd].subparsers[subsubcmd]
            if subsubparser.opts_value.get("-s", ["off"]) == ["on"]:
                self._s = True
            self._A = subsubparser.opts_value.get("-A", self._A)
            self._R = subsubparser.opts_value.get("-R", self._R)
            self._entries = subsubparser.value
            temp_A = []
            for key in self._A:
                if key in self._R:
                    temp_A.append(key)
                    self._R.remove(key)
            for temp in temp_A:
                self._A.remove(temp)

        if self.session.user_id not in permissions.users.get("owners", []) and (
            ("admins" in self._U and subcmd not in ("list", "info"))
            or ("owners" in self._U and subcmd not in ("list", "info"))
            or (self._t == "users" and ("admins" in self._A or "admins" in self._R))
            or (self._t == "users" and ("owners" in self._A or "owners" in self._R))
        ):
            await self.send_msg("非owners用户组成员不允许编辑owners和admins用户组")
            self.unlock()
            return

        if subcmd == "check":
            await self._check()
        if subcmd == "list":
            await self._list()
        if subcmd == "info":
            await self._info()
        if subcmd == "create":
            await self._create()
        if subcmd == "delete":
            await self._delete()
        if subcmd == "add":
            await self._add()
        if subcmd == "remove":
            await self._remove()
        if subsubcmd == "whitelist":
            await self._whitelist()
        if subsubcmd == "whites":
            await self._whites()
        if subsubcmd == "blacks":
            await self._blacks()

        self.unlock()
