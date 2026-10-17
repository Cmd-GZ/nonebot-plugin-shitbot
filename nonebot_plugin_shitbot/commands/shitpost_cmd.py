from __future__ import annotations

import asyncio
import math
import random
import time
from pathlib import Path
from typing import Any

import yaml
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.log import logger

from ..aux import is_sha256, validate_schema
from ..command import BotCommand
from ..msgdatabase import BotMsgDataBase
from ..msgutils import (
    DumpedMsg,
    dump_message,
    undump_message,
)
from ..parser import BotArgParser
from ..session import BotSession
from ..tasks import shitpost_lock
from .shitpost_main_cmd import BotCommandShitPostMain

_META_SCHEMA = {
    "sent": [int],
    "failed": int,
    "timestamp": int,
}


class BotCommandShitpost(BotCommand):
    _name: str = "shitpost"
    _shitpost_dir: Path = BotCommandShitPostMain.shitpost_dir
    _setting_path: Path = BotCommandShitPostMain.setting_path
    _meta_dir: Path = BotCommandShitPostMain.meta_dir
    _database: BotMsgDataBase

    def __init__(
        self, bot: Bot, session: BotSession, *, _pid: int, _internal: Any = None
    ) -> None:
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._a: list[int] = []
        self._d: list[int] = []
        self._min: int | None = None
        self._max: int | None = None
        self._has_auto: bool = False
        self._has_sent: bool = False
        self._failed: int | None = None
        self._before: str | None = None
        self._to: list[int] = []
        self._no_here: bool = False
        self._groups: list[int] = []
        self._sha256s: list[str] = []

        self._astate: str = ""
        self._is_accept_msg: bool = False
        self._roger_lock: asyncio.Lock = asyncio.Lock()
        self._reply: DumpedMsg | None = None

    def _init_parser(self) -> BotArgParser:
        parser = BotArgParser()
        parser.set_rule(max=0, need_subcmd=True)
        start = parser.add_subparser("start")
        stop = parser.add_subparser("stop")
        add = parser.add_subparser("add")
        _del = parser.add_subparser("del")
        _set = parser.add_subparser("set")
        mark = parser.add_subparser("mark")
        check = parser.add_subparser("check")
        send = parser.add_subparser("send")
        status = parser.add_subparser("status")

        start.set_rule(max=0)
        start.add_opt("--auto")

        stop.set_rule(max=0)
        stop.add_opt("--auto")

        add.set_rule(max=0, need_subcmd=True)
        begin = add.add_subparser("begin")
        end = add.add_subparser("end")
        reply = add.add_subparser("reply")
        begin.set_rule(types=[int])
        begin.add_opt("--no-here")
        end.set_rule(max=0)
        reply.set_rule(types=[int])
        reply.add_opt("--no-here")

        _del.set_rule()
        _del.add_opt("--sent")
        _del.add_opt("--failed", required=True, type=int)
        _del.add_opt("--before", required=True)

        _set.set_rule(max=0)
        _set.add_opt("-a", required=True, type=int, max_appeared=None)
        _set.add_opt("-d", required=True, type=int, max_appeared=None)
        _set.add_opt("--min", required=True, type=int)
        _set.add_opt("--max", required=True, type=int)

        mark.set_rule()
        mark.add_opt("-a", required=True, type=int, max_appeared=None)
        mark.add_opt("-d", required=True, type=int, max_appeared=None)

        check.set_rule()

        send.set_rule()
        send.add_opt("--to", required=True, type=int, max_appeared=None)

        status.set_rule(max=0)
        return parser

    async def _guard_state(self, subsubcmd: str | None = None) -> bool:
        if subsubcmd not in ["begin", "end"]:
            return await super()._guard_state()
        if subsubcmd == "begin" and self._argv is not None:
            return await super()._guard_state()
        if subsubcmd == "end" and self._argv is None:
            tip = "错误：会话未开始\n"
            tip += "尚未开始赤食，请先使用 /shitpost add begin 开始收集。"
            await self.send_msg(tip)
            self.unlock()
            return False
        if subsubcmd == "end" and self._astate != "begin":
            return await super()._guard_state()

        return True

    async def _get_reply_msg(self, args: Message) -> DumpedMsg | None:
        res = None
        if not args or args[0].type != "reply":
            return None
        try:
            reply = await self.bot.get_msg(message_id=args[0].data["id"])
            res = await dump_message(self.bot, undump_message(reply["message"]))
        except Exception as e:
            logger.error(f"获取回复消息失败: {e}")
            return None
        return res

    def _load_setting(self) -> dict[str, Any]:
        try:
            setting = yaml.safe_load(self._setting_path.read_text(encoding="utf-8"))
        except Exception:
            setting = None
        return setting or {"groups": [], "min": 60, "max": 300, "is_auto": False}

    def _load_meta(self, sha256: str) -> dict[str, Any] | None:
        try:
            if not is_sha256(sha256):
                return None
            meta = yaml.safe_load((self._meta_dir / sha256).read_text(encoding="utf-8"))
            if not validate_schema(meta, _META_SCHEMA):
                return None
        except Exception:
            meta = None
        return meta

    def _load_meta_all(self) -> dict[str, dict[str, Any] | None]:
        metas = {}
        for meta_path in self._meta_dir.iterdir():
            sha256 = meta_path.name
            metas[sha256] = self._load_meta(sha256)
        return metas

    def _get_service(self) -> BotCommandShitPostMain | None:
        spsession = BotSession.get_obj("public", "shitpost")
        if spsession is None:
            return None
        main_command = spsession.commands.get(spsession.curpid)
        if not isinstance(main_command, BotCommandShitPostMain):
            return None
        return main_command

    def _update_setting(self, setting: dict[str, Any]) -> None:
        self._setting_path.write_text(
            yaml.safe_dump(setting, allow_unicode=True), encoding="utf-8"
        )

        main_command = self._get_service()
        if main_command is not None:
            main_command.load_setting()

    def _update_meta(self, sha256: str, meta: dict[str, Any]) -> None:
        if not is_sha256(sha256):
            return
        meta_path = self._meta_dir / sha256
        meta_path.write_text(yaml.safe_dump(meta, allow_unicode=True), encoding="utf-8")

        main_command = self._get_service()
        if main_command is not None:
            main_command.load_metas([sha256])

    async def _save_shit(self, msg: DumpedMsg) -> str | None:
        path = await self._database.save_msg(msg, cover=False)
        if path is None:
            return None
        sha256 = path.name
        if is_sha256(sha256) and not (self._meta_dir / sha256).exists():
            self._database.inc_msg_rc(sha256)
        return sha256

    def _del_shit(self, sha256s: list[str]) -> None:
        for sha256 in sha256s:
            self._database.dec_msg_rc(sha256)
            self._database.del_msg(sha256)
            if is_sha256(sha256):
                (self._meta_dir / sha256).unlink(missing_ok=True)

    async def _store_shit(self, msg: Message|DumpedMsg) -> None:
        dumped_msg = await dump_message(self.bot, msg) if isinstance(msg, Message) else msg
        async with shitpost_lock:
            sha256 = await self._save_shit(dumped_msg)
            if sha256 is None:
                await self.send_msg("错误: 收集失败")
                return
            meta = self._load_meta(sha256)
            if meta is None:
                meta = {"timestamp": int(time.time()), "failed": 0, "sent": []}
            meta["sent"] = list(set(meta["sent"] + self._groups))
            self._update_meta(sha256, meta)
        await self.send_msg(sha256)

    async def _remove_nonexist_groups(self, groups: list[int]) -> None:
        exist_groups = [group["group_id"] for group in await self.bot.get_group_list()]
        nonexist_groups = [group for group in groups if group not in exist_groups]
        for group in nonexist_groups:
            await self.send_msg(f"警告: bot不在群组 {group} 中")
            groups.remove(group)

    async def _start(self) -> None:
        shitpost_session = BotSession.make("public", "shitpost")
        main_command = BotCommandShitPostMain.make(
            self.bot, shitpost_session, _pid=shitpost_session.curpid
        )
        if main_command is None:
            await self.send_msg("警告: 搬史服务正在运行中")
        else:
            await main_command.run(Message())
        if self._has_auto:
            setting = self._load_setting()
            setting["is_auto"] = True
            async with shitpost_lock:
                self._update_setting(setting)
        await self.send_msg("搬史服务已开启")
        self.unlock()

    async def _stop(self) -> None:
        shitpost_session = BotSession.get_obj("public", "shitpost")
        if (
            shitpost_session is None
            or (main_command := shitpost_session.commands.get(shitpost_session.curpid))
            is None
        ):
            await self.send_msg("警告: 搬史服务未开启")
            self.unlock()
            return
        main_command.unlock()
        if self._has_auto:
            setting = self._load_setting()
            setting["is_auto"] = False
            async with shitpost_lock:
                self._update_setting(setting)
        await self.send_msg("搬史服务已关闭")
        self.unlock()

    async def _add_begin(self, groups: list[int]) -> None:
        if self.session is None:
            return
        self._groups = list(set(groups))
        await self._remove_nonexist_groups(self._groups)
        group_id = int(self.session.group_id) if self.session.group_id != "private" else None
        self._groups += [group_id] if not self._no_here and group_id is not None and group_id not in self._groups else []
        await self.send_msg("收集开始")
        self._astate = "begin"
        self._is_accept_msg = True

    async def _add_end(self) -> None:
        self._astate = "end"
        self._is_accept_msg = False
        async with self._roger_lock:
            await self.send_msg("收集结束")
            self.unlock()

    async def _add_reply(self, groups: list[int]) -> None:
        if self.session is None:
            return
        self._astate = "reply"
        if self._reply is None:
            await self.send_msg("错误: 未识别到被回复信息")
            self.unlock()
            return
        self._groups = list(set(groups))
        await self._remove_nonexist_groups(self._groups)
        group_id = int(self.session.group_id) if self.session.group_id != "private" else None
        self._groups += [group_id] if not self._no_here and group_id is not None and group_id not in self._groups else []
        await self._store_shit(self._reply)
        self.unlock()


    async def _del__get_before_stamp(self) -> int:
        if self._before is None:
            return 0
        try:
            time_seq = self._before.split(":")
            return (
                int(time.time())
                - int(time_seq[0]) * 60 * 60 * 24
                - int(time_seq[1]) * 60 * 60
                - int(time_seq[2]) * 60
                - int(time_seq[3])
            )
        except Exception:
            await self.send_msg("警告：时间格式错误，格式为 DD:HH:MM:SS, 将忽略此项")
            return 0

    async def _del(self) -> None:
        metas = {}
        target_groups = [-1]
        useless_sha256s = set(self._sha256s)
        failed_bound = self._failed if self._failed is not None else math.inf
        before_stamp = await self._del__get_before_stamp()

        if self._has_sent or self._failed is not None or self._before is not None:
            async with shitpost_lock:
                metas = self._load_meta_all()
        if self._has_sent:
            async with shitpost_lock:
                target_groups = self._load_setting().get("groups", []) or [-1]

        for sha256 in set(useless_sha256s):
            if not is_sha256(sha256) or not await self._database.has_msg(sha256):
                await self.send_msg(f"警告：{sha256} 不存在")
                useless_sha256s.remove(sha256)

        if self._reply is not None:
            async with shitpost_lock:
                reply_sha256 = await self._database.has_msg(self._reply)
            if reply_sha256 is None:
                await self.send_msg("警告：被回复消息不在库中")
            else:
                useless_sha256s.add(reply_sha256)

        for sha256, meta in metas.items():
            if meta is None:
                continue
            if all(group in meta["sent"] for group in target_groups):
                useless_sha256s.add(sha256)
            if meta["failed"] >= failed_bound:
                useless_sha256s.add(sha256)
            if meta["timestamp"] <= before_stamp:
                useless_sha256s.add(sha256)

        async with shitpost_lock:
            self._del_shit(list(useless_sha256s))
        await self.send_msg("删除成功")
        self.unlock()

    async def _set(self) -> None:
        async with shitpost_lock:
            setting = self._load_setting()
        new_groups = list(set(setting["groups"]))
        cap = set(self._a).intersection(self._d)
        self._a = list(set(self._a) - cap)
        self._d = list(set(self._d) - cap)
        await self._remove_nonexist_groups(self._a)
        for group in self._a:
            if group in new_groups:
                await self.send_msg(f"警告：群组 {group} 已存在")
            new_groups.append(group)
        for group in self._d:
            if group not in new_groups:
                await self.send_msg(f"警告：群组 {group} 不存在")
                continue
            new_groups.remove(group)
        setting["groups"] = new_groups
        new_min = self._min if self._min is not None else setting["min"]
        new_max = self._max if self._max is not None else setting["max"]
        if new_min > new_max or new_min < 0 or new_max < 0:
            await self.send_msg("警告：最小值大于最大值或有小于0的值, 将忽略此项")
        else:
            setting["min"] = new_min
            setting["max"] = new_max
        async with shitpost_lock:
            self._update_setting(setting)
        await self.send_msg("设置完毕")
        self.unlock()

    async def _mark__sent(self, meta: dict[str, Any]) -> None:
        for group in self._a:
            if group in meta["sent"]:
                await self.send_msg(f"警告：群组 {group} 已存在")
                continue
            meta["sent"].append(group)
        for group in self._d:
            if group not in meta["sent"]:
                await self.send_msg(f"警告：群组 {group} 不存在")
                continue
            meta["sent"].remove(group)

    async def _mark__msg(self, sha256: str) -> None:
        async with shitpost_lock:
            meta = self._load_meta(sha256)
            if meta is None:
                await self.send_msg(f"警告：{sha256} 不存在")
                return
            await self._mark__sent(meta)
            self._update_meta(sha256, meta)

    async def _mark(self) -> None:
        cap = set(self._a).intersection(self._d)
        self._a = list(set(self._a) - cap)
        self._d = list(set(self._d) - cap)
        await self._remove_nonexist_groups(self._a)
        for sha256 in self._sha256s:
            await self._mark__msg(sha256)
        await self.send_msg("更新完毕")
        self.unlock()

    async def _check(self) -> None:
        if self._reply is not None:
            async with shitpost_lock:
                reply_sha256 = await self._database.has_msg(self._reply)
            if reply_sha256 is None:
                await self.send_msg(f"被回复的信息: {False}")
            else:
                await self.send_msg(f"被回复的信息({reply_sha256}): {True}")
        for sha256 in self._sha256s:
            async with shitpost_lock:
                meta = self._load_meta(sha256)
            await self.send_msg(f"{sha256}: {meta is not None}")
        self.unlock()

    async def _send__init_targets(self) -> dict[int | None, list[tuple[str, Message]]]:
        send_map = {}
        self._to = list(set(self._to))
        await self._remove_nonexist_groups(self._to)
        for group in self._to:
            send_map[group] = []
        if not send_map and not self._to and self.session:
            group_id = (
                int(self.session.group_id)
                if self.session.group_id != "private"
                else None
            )
            send_map[group_id] = []
        return send_map

    async def _send__get_msgs(
        self, send_map: dict[int | None, list[tuple[str, Message]]]
    ) -> None:
        for sha256 in self._sha256s:
            async with shitpost_lock:
                meta = self._load_meta(sha256)
            if meta is None:
                await self.send_msg(f"警告：{sha256} 不存在")
                continue
            for value in send_map.values():
                value.append((sha256, self._database.prepare_send_msg(sha256)))

    async def _send__find_msg(
        self, file_list: list[Path], key: int | None, value: list[tuple[str, Message]]
    ) -> None:
        random_sha256s = [file.name for file in file_list]
        random.shuffle(random_sha256s)
        for sha256 in random_sha256s:
            async with shitpost_lock:
                meta = self._load_meta(sha256)
            if meta is not None and key not in meta["sent"]:
                value.append((sha256, self._database.prepare_send_msg(sha256)))
                return
        if not value:
            await self.send_msg(f"警告：数据库中的史均已在群组 {key} 中发送过")

    async def _send__find_msgs(
        self, send_map: dict[int | None, list[tuple[str, Message]]]
    ) -> None:
        if not self._meta_dir.exists():
            return
        file_list = list(self._meta_dir.iterdir())
        if any(value for value in send_map.values()) or all(
            not f.is_file() for f in file_list
        ):
            return
        for key, value in send_map.items():
            await self._send__find_msg(file_list, key, value)

    def _send__save_meta(self, sha256: str, group_id: int | None) -> None:
        meta = self._load_meta(sha256)
        if meta is None:
            return
        if group_id not in meta["sent"]:
            meta["sent"].append(group_id)
        self._update_meta(sha256, meta)

    async def _send__send_msg(
        self, group_id: int | None, value: list[tuple[str, Message]]
    ) -> None:
        for sha256, msg in value:
            await self.send_msg(
                msg, group_id=str(group_id) if group_id is not None else None
            )
            if group_id is None:
                continue
            async with shitpost_lock:
                self._send__save_meta(sha256, group_id)

    async def _send__send_msgs(
        self, send_map: dict[int | None, list[tuple[str, Message]]]
    ) -> None:
        for group_id, value in send_map.items():
            await self._send__send_msg(group_id, value)

    async def _send(self) -> None:
        send_map = await self._send__init_targets()
        await self._send__get_msgs(send_map)
        await self._send__find_msgs(send_map)
        await self._send__send_msgs(send_map)
        self.unlock()

    async def _status(self) -> None:
        async with shitpost_lock:
            shit_count = len(list(self._meta_dir.iterdir()))
            setting = self._load_setting()
        await self.send_msg(
            f"当前库内史存量：{shit_count}\n"
            + f"当前目标群组：{setting['groups']}\n"
            + f"当前最小发送时间间隔：{setting['min']}\n"
            + f"当前最大发送时间间隔：{setting['max']}"
        )
        self.unlock()

    async def roger(self, event: MessageEvent) -> None:
        async with self._roger_lock:
            if not self._is_accept_msg:
                return
            await self._store_shit(event.message)

    async def run(self, args: Message) -> None:
        if not self.session:
            return
        async with shitpost_lock:
            self._database = BotMsgDataBase(self._shitpost_dir)
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

        self._argv = new_argv

        if not self._check_perm("shitpost") or (
            not self._check_perm("shitpostmanager") and subcmd != "send"
        ):
            await self.send_msg("权限不足")
            self.unlock()
            return

        self._reply = await self._get_reply_msg(args)
        if subcmd == "start" or subcmd == "stop":
            self._has_auto = subparser.opts_value.get("--auto") != []
        if subcmd == "add" and subsubcmd in ["begin", "reply"]:
            self._no_here = bool(
                subparser.subparsers[subsubcmd].opts_value.get("--no-here")
            )
        if subcmd in ["del", "mark", "check", "send"]:
            self._sha256s = subparser.value
        if subcmd == "del":
            self._has_sent = bool(subparser.opts_value.get("--sent"))
            if subparser.opts_value.get("--failed"):
                self._failed = subparser.opts_value["--failed"][0]
            if subparser.opts_value.get("--before"):
                self._before = subparser.opts_value["--before"][0]
        if subcmd == "set" or subcmd == "mark":
            if _a := subparser.opts_value.get("-a"):
                self._a = _a
            if _d := subparser.opts_value.get("-d"):
                self._d = _d
        if subcmd == "set":
            if _min := subparser.opts_value.get("--min"):
                self._min = _min[0]
            if _max := subparser.opts_value.get("--max"):
                self._max = _max[0]
        if subcmd == "send" and self._check_perm("shitpostmanager"):
            self._to = subparser.opts_value.get("--to", [])

        if subcmd == "start":
            await self._start()
        if subcmd == "stop":
            await self._stop()
        if subcmd == "add" and subsubcmd == "begin":
            subsubparser = subparser.subparsers[subsubcmd]
            await self._add_begin(subsubparser.value)
        if subcmd == "add" and subsubcmd == "end":
            await self._add_end()
        if subcmd == "add" and subsubcmd == "reply":
            subsubparser = subparser.subparsers[subsubcmd]
            await self._add_reply(subsubparser.value)
        if subcmd == "del":
            await self._del()
        if subcmd == "set":
            await self._set()
        if subcmd == "mark":
            await self._mark()
        if subcmd == "check":
            await self._check()
        if subcmd == "send":
            await self._send()
        if subcmd == "status":
            await self._status()
