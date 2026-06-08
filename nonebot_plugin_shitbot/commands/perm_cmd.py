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
        entry.set_rule(max=0, need_subcmd=True)
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

    @staticmethod
    def _invert(flag: bool, exp: bool):
        if flag:
            return not exp
        return exp

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
        tip = "权限元素信息:\n"
        for title, elems, elemsdic in (
            ("用户权限组:\n", self._U, permissions.users),
            ("群组权限组:\n", self._G, permissions.groups),
            ("权限项:\n", self._E, permissions.entries),
        ):
            tip += title
            for key in elems:
                tip += f"{key}:\n{elemsdic.get(key, '未创建')}\n"
        await self.send_msg(tip)

    async def _perm_group(self, mode: str):
        if self.session is None or mode not in ["create", "delete"]:
            return
        verb = "创建" if mode == "create" else "删除"
        flag = False if mode == "create" else True
        ptcl = "已" if mode == "create" else "不"

        def _op(flag: bool, dic: dict, key: str):
            if flag:
                return dic.pop(key)
            dic[key] = []

        try:
            for perms, permsdic, updatefunc, norm in (
                (self._U, permissions.users, permissions.update_users, "用户"),
                (self._G, permissions.groups, permissions.update_groups, "群组"),
            ):
                is_edited = False
                for key in perms:
                    if self._invert(flag, (key in permsdic)):
                        await self.send_msg(f"警告: {norm}权限组 {key} {ptcl}存在")
                        continue
                    _op(flag, permsdic, key)
                    is_edited = True
                if is_edited:
                    updatefunc()

            await self.send_msg(f"{verb}成功")
        except Exception as e:
            await self.send_msg(f"{verb}失败：{e}")

    async def _perm_mem(self, mode: str):
        if self.session is None or mode not in ["add", "remove"]:
            return
        verb = "添加" if mode == "add" else "移除"
        flag = False if mode == "add" else True
        ptcl = "已" if mode == "add" else "不"

        def _op(flag: bool, list: list, elem: str):
            if flag:
                return list.remove(elem)
            list.append(elem)

        try:
            for perms, mems, permsdic, updatefunc, norm in (
                (self._U, self._u, permissions.users, permissions.update_users, "用户"),
                (
                    self._G,
                    self._g,
                    permissions.groups,
                    permissions.update_groups,
                    "群组",
                ),
            ):
                length = min(len(perms), len(mems))
                is_edited = False
                for i in range(length):
                    perm = permsdic.get(perms[i])
                    if perm is None:
                        await self.send_msg(f"警告: {norm}权限组 {perms[i]} 不存在")
                        continue
                    if self._invert(flag, (mems[i] in perm)):
                        await self.send_msg(
                            f"警告: {norm}权限组 {perms[i]} 中{ptcl}存在{norm} {mems[i]}"
                        )
                        continue
                    _op(flag, perm, mems[i])
                    is_edited = True
                if is_edited:
                    updatefunc()

            await self.send_msg(f"{verb}成功")
        except Exception as e:
            await self.send_msg(f"{verb}失败：{e}")

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

    async def _perm_entry(self, mode: str):
        if self.session is None or mode not in ["whites", "blacks"]:
            return
        adj = "白" if mode == "whites" else "黑"

        def _op(flag: bool, list: list, elem: str):
            if flag:
                return list.remove(elem)
            list.append(elem)

        try:
            is_edited = False
            for key in self._entries:
                if key not in permissions.entries:
                    await self.send_msg(f"警告: 权限项 {key} 不存在")
                    continue
                perms_list = permissions.entries[key][self._t][mode]
                for operated_list, flag, ptcl in (
                    (self._A, False, "已"),
                    (self._R, True, "不"),
                ):
                    for perms in operated_list:
                        if self._invert(flag, (perms in perms_list)):
                            await self.send_msg(
                                f"警告: 权限项 {key} 的{adj}名单中{ptcl}存在权限组 {perms}"
                            )
                            continue
                        _op(flag, perms_list, perms)
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

        if not await self._guard_state():
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        subcmd = self._parser.subcmd
        if subcmd is None:
            self.unlock()
            return
        subsubcmd = None

        no_manager = not permissions.owners_check_permission(
            "permmanager", self.session.group_id, self.session.user_id
        ) and not self._check_perm("permmanager")

        if (no_manager and subcmd != "check") or (
            subcmd == "check" and not self._check_perm("perm") and no_manager
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
        if subcmd in ("create", "delete"):
            await self._perm_group(subcmd)
        if subcmd in ("add", "remove"):
            await self._perm_mem(subcmd)
        if subsubcmd == "whitelist":
            await self._whitelist()
        if subsubcmd in ("whites", "blacks"):
            await self._perm_entry(subsubcmd)

        self.unlock()
