import asyncio
from pathlib import Path

import yaml
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent

from ..command import BotCommand
from ..msgdatabase import BotMsgDataBase
from ..msgutils import (
    DataVariables,
    DumpedMsg,
    DumpedSeg,
    dump_message,
    modify_msg_data,
    msg_filter,
)
from ..parser import BotArgParser
from ..session import BotSession
from ..tasks import autoreply_lock
from .autoreply_main_cmd import BotCommandAutoReplyMain


class BotCommandAutoreply(BotCommand):
    _name = "autoreply"
    _autoreply_dir = BotCommandAutoReplyMain._autoreply_dir
    _rule_path = BotCommandAutoReplyMain._rule_path
    _msg_table_path = BotCommandAutoReplyMain._msg_table_path

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._roger_lock = asyncio.Lock()
        self._is_accept_msg = False
        self._rule = {}
        self._msg_table = {}
        self._temp_msg: DumpedMsg = []

        self._auto: bool = False
        self._key: list[str] = []
        self._rp: list[str] = []
        self._T: list[str] = []
        self._t: list[str] = []
        self._D: list[str] = []
        self._d: list[str] = []
        self._K: list[str] = []
        self._k: list[str] = []
        self._R: list[str] = []
        self._r: list[str] = []
        self._m: int = -1
        self._l: int = 0
        self._sum: list[str] = []
        self._st: list[int] = []

        self._rstate: str = ""

    def _load_meta(self):
        if not self._rule_path.exists() or not self._msg_table_path.exists():
            raise FileNotFoundError
        _rule = yaml.safe_load(self._rule_path.read_text(encoding="utf-8"))
        _msg_table = yaml.safe_load(self._msg_table_path.read_text(encoding="utf-8"))
        if (_rule is not None and not isinstance(_rule, dict)) or (
            _msg_table is not None and not isinstance(_msg_table, dict)
        ):
            raise ValueError
        self._rule = _rule if _rule is not None else {}
        self._msg_table = _msg_table if _msg_table is not None else {}

    def _update_meta(self):
        self._rule_path.write_text(
            yaml.safe_dump(self._rule, allow_unicode=True), encoding="utf-8"
        )
        self._msg_table_path.write_text(
            yaml.safe_dump(self._msg_table, allow_unicode=True), encoding="utf-8"
        )
        arsession = BotSession.get_obj("public", "autoreply")
        if arsession is None:
            return
        main_command = arsession.commands.get(arsession.curpid)
        if main_command is None or not isinstance(
            main_command, BotCommandAutoReplyMain
        ):
            return
        main_command.load_meta()

    async def _set_reply(self, reply: str):
        old_msg_hash = self._msg_table.get(reply, "")
        if self._temp_msg == []:
            if old_msg_hash:
                return
            self._msg_table[reply] = ""
            self._update_meta()
            return

        def _filter(seg: DumpedSeg) -> bool:
            return seg["type"] in ["text", "image", "face"]

        filtered_msg = msg_filter(_filter, self._temp_msg)
        msg_path = await self._database.save_msg(filtered_msg)
        msg_hash = msg_path.name
        self._msg_table[reply] = msg_hash
        self._database.inc_msg_rc(msg_hash)
        if old_msg_hash:
            self._database.dec_msg_rc(old_msg_hash)
            self._database.del_msg(old_msg_hash)
        self._update_meta()

    def _del_reply(self, reply: str):
        for key in self._rule.keys():
            if reply in self._rule[key]["replys"]:
                self._rule[key]["replys"].remove(reply)
        msg_hash = self._msg_table.get(reply, "")
        if not msg_hash:
            self._msg_table.pop(reply, None)
            self._update_meta()
            return
        self._database.dec_msg_rc(msg_hash)
        self._database.del_msg(msg_hash)
        self._msg_table.pop(reply, None)
        self._update_meta()

    def _set_key(
        self,
        key: str,
        *,
        trans: list[str] | None = None,
        dels: list[str] | None = None,
        is_contain: bool | None = None,
        keywords: list[str] | None = None,
        replys: list[str] | None = None,
    ):
        if key not in self._rule:
            self._rule[key] = {
                "trans": [],
                "dels": [],
                "is_contain": False,
                "keywords": [],
                "replys": [],
            }
        if trans is not None:
            self._rule[key]["trans"] = trans
        if dels is not None:
            self._rule[key]["dels"] = dels
        if is_contain is not None:
            self._rule[key]["is_contain"] = is_contain
        if keywords is not None:
            self._rule[key]["keywords"] = keywords
        if replys is not None:
            self._rule[key]["replys"] = replys
        self._update_meta()

    def _del_key(self, key: str):
        self._rule.pop(key, None)
        self._update_meta()

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0, need_subcmd=True)
        start = parser.add_subparser("start")
        stop = parser.add_subparser("stop")
        lst = parser.add_subparser("list")
        info = parser.add_subparser("info")
        prnt = parser.add_subparser("print")
        create = parser.add_subparser("create")
        delete = parser.add_subparser("delete")
        reply = parser.add_subparser("reply")
        key = parser.add_subparser("key")

        start.set_rule(max=0)
        start.add_opt("--auto", default=[0])

        stop.set_rule(max=0)
        stop.add_opt("--auto", default=[0])

        lst.set_rule(min=1, max=1)

        info.set_rule(max=None)

        prnt.set_rule(max=None)

        create.set_rule(max=0)
        create.add_opt("--key", required=True, max_appeared=None)
        create.add_opt("--rp", required=True, max_appeared=None)

        delete.set_rule(max=0)
        delete.add_opt("--key", required=True, max_appeared=None)
        delete.add_opt("--rp", required=True, max_appeared=None)

        reply.set_rule(min=1, max=1, need_subcmd=True)
        reply_start = reply.add_subparser("start")
        reply_stop = reply.add_subparser("stop")
        reply_modify = reply.add_subparser("modify")

        key.set_rule(min=1, max=1)
        key.add_opt(
            "-T",
            required=True,
            choice=["delmark", "delspace", "upper", "lower"],
            max_appeared=None,
        )
        key.add_opt(
            "-t",
            required=True,
            choice=["delmark", "delspace", "upper", "lower"],
            max_appeared=None,
        )
        key.add_opt("-D", required=True, max_appeared=None)
        key.add_opt("-d", required=True, max_appeared=None)
        key.add_opt("-K", required=True, max_appeared=None)
        key.add_opt("-k", required=True, max_appeared=None)
        key.add_opt("-R", required=True, max_appeared=None)
        key.add_opt("-r", required=True, max_appeared=None)
        key.add_opt("-m", required=True, choice=["equal", "contain"], default=[""])

        reply_start.set_rule(max=0)
        reply_start.add_opt("-l", required=True, type=int, default=[1])

        reply_stop.set_rule(max=0)

        reply_modify.set_rule(max=0)
        reply_modify.add_opt("--sum", required=True, max_appeared=None)
        reply_modify.add_opt("--st", required=True, type=int, max_appeared=None)

        return parser

    async def _guard_state(self, subsubcmd=None):
        if subsubcmd is None:
            return await super()._guard_state()
        if subsubcmd == "start" and self._argv is not None:
            return await super()._guard_state()
        if subsubcmd == "stop" and self._argv is None:
            tip = "错误：会话未开始\n"
            tip += "尚未开始收集自动信息，请先使用 /autoreply value start 开始收集。"
            await self.send_msg(tip)
            self.unlock()
            return False
        if subsubcmd == "stop" and self._rstate != "start":
            return await super()._guard_state()
        return True

    async def _start(self):
        autoreply_session = BotSession.make("public", "autoreply")
        main_command = BotCommandAutoReplyMain.make(
            self.bot, autoreply_session, _pid=autoreply_session.curpid
        )
        if main_command is None:
            await self.send_msg("警告: 自动回复正在运行中")
        else:
            await main_command.run(Message())
        if self._auto:
            from ruamel.yaml import YAML

            config_path = Path(__file__).parent.parent / "config.yaml"
            config_yaml = YAML()
            data = config_yaml.load(config_path)
            data["if_auto_start_autoreply"] = True
            config_yaml.dump(data, config_path)
        await self.send_msg("自动回复已开启")
        self.unlock()

    async def _stop(self):
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
        if self._auto:
            from ruamel.yaml import YAML

            config_path = Path(__file__).parent.parent / "config.yaml"
            config_yaml = YAML()
            data = config_yaml.load(config_path)
            data["if_auto_start_autoreply"] = False
            config_yaml.dump(data, config_path)
        await self.send_msg("自动回复已关闭")
        self.unlock()

    async def _list(self, tpe: str):
        lst = []
        if tpe == "key":
            lst = self._rule.keys()
        if tpe == "reply":
            lst = self._msg_table.keys()
        await self.send_msg("\n".join(lst))
        self.unlock()

    async def _info(self, keys: list[str]):
        tip = ""
        for key in keys:
            tip += f"{key}: {self._rule[key] if key in self._rule else '未创建'}\n"

        await self.send_msg(tip)
        self.unlock()

    async def _print(self, replys: list[str]):
        for reply in replys:
            await self.send_msg(f"{reply} 内容:")
            if reply not in self._msg_table:
                await self.send_msg(f"警告: {reply} 未被创建")
                continue
            if self._msg_table[reply] == "":
                await self.send_msg(f"警告: {reply} 未被设置")
                continue
            msg_hash = self._msg_table[reply]
            async with autoreply_lock:
                msg = self._database.prepare_send_msg(msg_hash)
            try:
                await self.send_msg(msg)
            except Exception as e:
                await self.send_msg(f"警告: {reply} 发送失败: {e}")

        self.unlock()

    async def _create(self):
        async with autoreply_lock:
            for key in self._key:
                if key in self._rule:
                    await self.send_msg(f"警告: 键 {key} 已存在")
                    continue
                self._set_key(key)
            for reply in self._rp:
                if reply in self._msg_table:
                    await self.send_msg(f"警告: 回复 {reply} 已存在")
                    continue
                await self._set_reply(reply)
            await self.send_msg("创建成功")

        self.unlock()

    async def _delete(self):
        async with autoreply_lock:
            for key in self._key:
                if key not in self._rule:
                    await self.send_msg(f"警告: 键 {key} 不存在")
                    continue
                self._del_key(key)
            for reply in self._rp:
                if reply not in self._msg_table:
                    await self.send_msg(f"警告: 回复 {reply} 不存在")
                    continue
                self._del_reply(reply)
            await self.send_msg("删除成功")

        self.unlock()

    async def _reply_start(self, reply_name: str):
        if reply_name not in self._msg_table:
            await self.send_msg(f"警告: 回复信息 {reply_name} 不存在")
            return
        self._rstate = "start"
        self._reply_name = reply_name
        await self.send_msg(
            f"请发送仅包含图片或文字的信息, 或者发送 /autoreply reply {reply_name} stop 停止设置"
        )
        self._is_accept_msg = True

    async def _reply_stop(self, reply_name: str):
        if reply_name not in self._msg_table:
            await self.send_msg(f"警告: 回复信息 {reply_name} 不存在")
            return
        self._rstate = "stop"
        self._is_accept_msg = False
        async with self._roger_lock:
            if not self._temp_msg:
                await self.send_msg("错误: 未收到任何信息")
                self.unlock()
                return
            async with autoreply_lock:
                await self._set_reply(reply_name)
                self._temp_msg = []
            await self.send_msg("设置成功")
            self.unlock()

    async def _reply_modify(self, reply_name: str):
        reply_hash = self._msg_table.get(reply_name, "")
        if reply_hash == "":
            await self.send_msg(f"警告: 回复信息 {reply_name} 不存在或未设置")
            return
        async with autoreply_lock:
            self._temp_msg = self._database.get_msg(reply_hash)
            if not self._temp_msg:
                await self.send_msg("错误: 未收到任何信息")
                self.unlock()
                return
            self._temp_msg = modify_msg_data(
                self._temp_msg,
                {
                    "summary": DataVariables(self._sum),
                    "sub_type": DataVariables(self._st),
                },
                ["image"],
            )
            await self._set_reply(reply_name)
            self._temp_msg = []
        await self.send_msg("修改成功")
        self.unlock()

    async def _key_modify(self, key_name: str):
        if key_name not in self._rule:
            await self.send_msg(f"错误: 键 {key_name} 不存在")
            self.unlock()
            return

        def _rm_dup(lst_A: list, lst_R: list):
            dup = []
            for elem in lst_A:
                if elem in lst_R:
                    dup.append(elem)
            for elem in dup:
                lst_A.remove(elem)
                lst_R.remove(elem)
            return dup

        def _get_lst(lst_S, lst_A, lst_R):
            lst = lst_S[:]
            for elem in lst_A:
                if elem not in lst_R:
                    lst.append(elem)
            for elem in lst_R:
                if elem in lst_S:
                    lst.remove(elem)
            return lst

        for lst_A, lst_R in [
            (self._T, self._t),
            (self._D, self._d),
            (self._K, self._k),
            (self._R, self._r),
        ]:
            _rm_dup(lst_A, lst_R)
        for lst in [self._R, self._r]:
            rem = []
            for elem in lst:
                if self._msg_table.get(elem, "") == "":
                    await self.send_msg(f"警告: 回复信息 {elem} 不存在或未设置")
                    rem.append(elem)
            for elem in rem:
                lst.remove(elem)
        data = []
        for lst_S, lst_A, lst_R in [
            (self._rule[key_name]["trans"], self._T, self._t),
            (self._rule[key_name]["dels"], self._D, self._d),
            (self._rule[key_name]["keywords"], self._K, self._k),
            (self._rule[key_name]["replys"], self._R, self._r),
        ]:
            data.append(_get_lst(lst_S, lst_A, lst_R))

        _m = None
        if self._m == 0:
            _m = False
        elif self._m == 1:
            _m = True

        async with autoreply_lock:
            self._set_key(
                key_name,
                trans=data[0],
                dels=data[1],
                is_contain=_m,
                keywords=data[2],
                replys=data[3],
            )
        await self.send_msg("修改成功")
        self.unlock()

    async def roger(self, event: MessageEvent):
        async with self._roger_lock:
            if not self._is_accept_msg:
                return
            if self._l <= 0:
                return
            dumped_msg = await dump_message(self.bot, event.message)
            self._temp_msg.extend(dumped_msg)
            self._l -= 1
            if self._l <= 0:
                reply_name = getattr(self, "_reply_name", None)
                if reply_name is None:
                    raise ValueError
                asyncio.create_task(self.run(Message(f"reply {reply_name} stop")))

    async def run(self, args: Message):
        async with autoreply_lock:
            self._database = BotMsgDataBase(self._autoreply_dir)
            self._rule_path.touch(exist_ok=True)
            self._msg_table_path.touch(exist_ok=True)
            self._load_meta()

        if not self.session:
            return
        new_argv = args.extract_plain_text().strip().split()

        if not await self._legal_case(new_argv):
            if self._argv is None:
                self.unlock()
            return
        subsubcmd = None
        self._parser.parse_argv(new_argv)
        subcmd = self._parser.subcmd
        if subcmd is None:
            self.unlock()
            return
        subparser = self._parser.subparsers[subcmd]
        subsubcmd = subparser.subcmd

        if not await self._guard_state(subsubcmd):
            return

        if not self._check_perm("autoreplymanager"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        self._argv = new_argv

        _auto = subparser.opts_value.get("--auto", [0])[0]
        self._auto = _auto >= 1

        self._key = subparser.opts_value.get("--key", [])
        self._rp = subparser.opts_value.get("--rp", [])

        self._T = subparser.opts_value.get("-T", [])
        self._t = subparser.opts_value.get("-t", [])
        self._D = subparser.opts_value.get("-D", [])
        self._d = subparser.opts_value.get("-d", [])
        self._K = subparser.opts_value.get("-K", [])
        self._k = subparser.opts_value.get("-k", [])
        self._R = subparser.opts_value.get("-R", [])
        self._r = subparser.opts_value.get("-r", [])
        _ms = subparser.opts_value.get("-m", [""])
        if _ms[0] == "equal":
            self._m = 0
        if _ms[0] == "contain":
            self._m = 1

        if subsubcmd is not None:
            subsubparser = subparser.subparsers[subsubcmd]
            self._l = subsubparser.opts_value.get("-l", [1])[0]
            self._l = max(1, self._l)
            self._sum = subsubparser.opts_value.get("--sum", [])
            self._st = subsubparser.opts_value.get("--st", [])
            self._rstate = subsubcmd if subsubcmd != "modify" else ""

        if subcmd == "start":
            await self._start()
        if subcmd == "stop":
            await self._stop()
        if subcmd == "list":
            lst = subparser.value[0]
            await self._list(lst)
        if subcmd == "info":
            await self._info(subparser.value)
        if subcmd == "print":
            await self._print(subparser.value)
        if subcmd == "create":
            await self._create()
        if subcmd == "delete":
            await self._delete()
        reply_name = ""
        if subcmd == "reply":
            reply_name = subparser.value[0]
        if subsubcmd == "start":
            await self._reply_start(reply_name)
        if subsubcmd == "stop":
            await self._reply_stop(reply_name)
        if subsubcmd == "modify":
            await self._reply_modify(reply_name)
        if subcmd == "key":
            key_name = subparser.value[0]
            await self._key_modify(key_name)
