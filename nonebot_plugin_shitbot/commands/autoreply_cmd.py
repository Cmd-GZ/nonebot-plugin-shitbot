from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import httpx
import yaml
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.log import logger

from ..aux import rename_file_to_sha256, rm_cache, stuff_download
from ..command import BotCommand
from ..config import config
from ..msgutils import (
    DataVariables,
    DumpedMsg,
    DumpedSeg,
    dump_message,
    get_multimedias_url,
    modify_msg_data,
    msg_filter,
)
from ..parser import BotArgParser
from ..session import BotSession
from ..tasks import EndOfQueue, autoreply_lock, prod_cons
from .autoreply_main_cmd import BotCommandAutoReplyMain


# Will be reconstructed after I implement the database
class BotCommandAutoreply(BotCommand):
    _name = "autoreply"
    _autoreply_dir = BotCommandAutoReplyMain._autoreply_dir
    _rule_path = BotCommandAutoReplyMain._rule_path
    _msg_dir = BotCommandAutoReplyMain._msg_dir
    _image_dir = BotCommandAutoReplyMain._image_dir

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._k: list[str] = []
        self._v: list[str] = []
        self._vstate: str = ""
        self._l: int = 1
        self._sum: list[str] = []
        self._st: list[int] = []
        self._d: list[str] = []
        self._tm: list[str] = []
        self._m: str = "equal"

        self._prod_lock = asyncio.Lock()
        self._cons_lock = asyncio.Lock()
        self._is_accept_pic = False
        self._urls = asyncio.Queue()
        self._downloads = asyncio.Queue()
        self._pics = asyncio.Queue()

        self._rule = {}
        self._temp_msg: DumpedMsg = []

    async def _guard_state(self, new_argv=None):
        if new_argv is None:
            return False
        # If new_argv is not value --start or not value --stop, handle it as normal
        self._parser.parse_argv(new_argv)
        subcmd = self._parser.subcmd
        if subcmd != "value":
            return await super()._guard_state()
        subparser = self._parser.subparsers[subcmd]
        is_stop = subparser.opts_value["--stop"][0]
        is_start = subparser.opts_value["--start"][0] if not is_stop else 0
        if not is_start and not is_stop:
            return await super()._guard_state()

        # Handle the case where new_argv is value --start
        if self._argv is not None and is_start:
            return await super()._guard_state()
        if self._argv is None and is_start:
            return True

        # Handle the case where new_argv is value --stop and self._argv is None
        if self._argv is None and is_stop:
            tip = "错误：会话未开始\n"
            tip += "尚未开始收集自动信息，请先使用 /autoreply value --start 开始收集。"
            await self.send_msg(tip)
            self.unlock()
            return False
        if self._argv is None:
            return False

        # Now handle the case where new_argv is value --stop and self._argv is not None
        if self._vstate != "start":
            return await super()._guard_state()
        return True

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0, need_subcmd=True)

        start = parser.add_subparser("start")
        start.set_rule(max=0)

        stop = parser.add_subparser("stop")
        stop.set_rule(max=0)

        create = parser.add_subparser("create")
        create.set_rule(max=0)
        create.add_opt("-k", required=True, max_appeared=None)
        create.add_opt("-v", required=True, max_appeared=None)

        delete = parser.add_subparser("delete")
        delete.set_rule(max=0)
        delete.add_opt("-k", required=True, max_appeared=None)
        delete.add_opt("-v", required=True, max_appeared=None)

        value = parser.add_subparser("value")
        value.set_rule(min=1, max=1)
        value.add_opt("--stop", default=[0])
        value.add_opt("--start", default=[0])
        value.add_opt("-l", required=True, type=int, default=[1])
        value.add_opt("--sum", required=True, max_appeared=None)
        value.add_opt("--st", required=True, type=int, max_appeared=None)

        key = parser.add_subparser("key")
        key.set_rule(min=1, max=1)
        key.add_opt(
            "--tm",
            required=True,
            choice=["delspace", "delmarks", "uppercase", "lowercase"],
            max_appeared=None,
            default=[],
        )
        key.add_opt("-d", required=True, max_appeared=None, default=[])
        key.add_opt("-m", required=True, choice=["equal", "contain"], default=["equal"])
        key.add_opt("-v", required=True, max_appeared=None, default=[])

        return parser

    @staticmethod
    def _invert(flag: bool, exp: bool):
        if flag:
            return not exp
        return exp

    def _load_rule(self):
        _rule = yaml.safe_load(self._rule_path.read_text(encoding="utf-8"))
        if _rule is not None and not isinstance(_rule, dict):
            raise ValueError
        self._rule = _rule if _rule is not None else {}

    def _update_rule(self):
        with self._rule_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(self._rule, f, allow_unicode=True)
            arsession = BotSession.get_obj("public", "autoreply")
            if arsession is None:
                return
            main_command = arsession.commands.get(arsession.curpid)
            if main_command is None or not isinstance(
                main_command, BotCommandAutoReplyMain
            ):
                return
            main_command.load_rule()

    @staticmethod
    async def _url_to_download(
        download_url: str, client: httpx.AsyncClient, download_dir: Path
    ):
        try:
            filename = f"{uuid.uuid4().hex}"
            save_path = download_dir / filename
            await stuff_download(client, download_url, save_path)
            logger.info(f"下载图片成功: {save_path}")
            return str(save_path)
        except Exception as e:
            logger.error(f"下载图片失败 {download_url}: {e}")
            return ""

    @staticmethod
    async def _download_to_pic(download_path: str, pic_dir: Path):
        if download_path == "":
            return ""

        rename_path = rename_file_to_sha256(download_path)
        pic_path = pic_dir / rename_path.name
        async with autoreply_lock:
            if not pic_path.exists():
                rename_path.rename(pic_path)
        return str(pic_path)

    async def _start(self):
        autoreply_session = BotSession.make("public", "autoreply")
        main_command = BotCommandAutoReplyMain.make(
            self.bot, autoreply_session, _pid=autoreply_session.curpid
        )
        if main_command is None:
            await self.send_msg("警告: 自动回复正在运行中")
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
        await self.send_msg("自动回复已关闭")
        self.unlock()

    async def _create_delete(self, mode):
        if mode not in ["create", "delete"]:
            return

        verb = "创建" if mode == "create" else "删除"
        flag = not mode == "create"
        ptcl = "已" if mode == "create" else "不"

        def _op1(flag: bool, dic: dict, key: str):
            if flag:
                return dic.pop(key)
            dic[key] = [[], [], False, []]

        def _op2(flag: bool, path: Path):
            if flag:
                return path.unlink()
            path.touch(exist_ok=True)

        async with autoreply_lock:
            self._load_rule()
            is_edited = False
            for key in self._k:
                if self._invert(flag, key in self._rule):
                    await self.send_msg(f"警告: {key} {ptcl}存在")
                    continue
                _op1(flag, self._rule, key)
                is_edited = True
            if is_edited:
                self._update_rule()
            for value in self._v:
                value_path = self._msg_dir / f"{value}.yaml"
                if self._invert(flag, value_path.exists()):
                    await self.send_msg(f"警告: {value} {ptcl}存在")
                    continue
                _op2(flag, value_path)
            await self.send_msg(f"{verb}成功")
            self.unlock()

    async def _value_start(self, value_name: str):
        if self._session is None:
            return
        value_path = self._msg_dir / f"{value_name}.yaml"
        if not value_path.exists():
            await self.send_msg(f"错误: {value_name} 不存在")
            self.unlock()
            return
        downloads_dir = (
            config.cache
            / self._session.group_id
            / self._session.user_id
            / str(self._pid)
            / "autoreply"
        )
        downloads_dir.mkdir(parents=True, exist_ok=True)

        async def _urls_to_downloads():
            try:
                async with httpx.AsyncClient() as client:
                    await prod_cons(
                        self._urls,
                        self._downloads,
                        self._url_to_download,
                        client,
                        downloads_dir,
                    )
            except Exception as e:
                logger.exception(f"urls_to_downloads 管道异常退出: {e}")

        async def _downloads_to_pics():
            try:
                async with self._cons_lock:
                    await prod_cons(
                        self._downloads,
                        self._pics,
                        self._download_to_pic,
                        self._image_dir,
                    )
            except Exception as e:
                logger.exception(f"downloads_to_pics 管道异常退出: {e}")

        asyncio.create_task(_urls_to_downloads())
        asyncio.create_task(_downloads_to_pics())

        logger.info(f"用户 {self._session.user_id} 开始为 {value_name} 设置具体信息")
        await self.send_msg(
            f"请发送仅包含图片或文字的信息, 或者发送 /autoreply value --stop {value_name} 停止设置"
        )

        self._is_accept_pic = True
        self._value_name = value_name
        return

    async def _value_stop(self, value_name: str):
        if not self.session:
            return
        self._is_accept_pic = False

        async with self._prod_lock:
            await self._urls.put(EndOfQueue())
        async with self._cons_lock:
            pass

        pics = []
        while True:
            pic = await self._pics.get()
            if isinstance(pic, EndOfQueue):
                break
            pics.append(pic)

        self._temp_msg = modify_msg_data(
            self._temp_msg,
            {
                "file": DataVariables([f"{Path(path).name}" for path in pics]),
                "summary": DataVariables(self._sum),
                "sub_type": DataVariables(self._st),
            },
            ["image"],
            replace=True,
        )
        if self._temp_msg == []:
            await self.send_msg("错误: 未受到任何信息")
            await rm_cache(self.session.group_id, self.session.user_id, str(self._pid))
            self.unlock()
            return
        async with autoreply_lock:
            value_path = self._msg_dir / f"{value_name}.yaml"
            value_path.write_text(yaml.safe_dump(self._temp_msg))

        await self.send_msg("设置成功")
        await rm_cache(self.session.group_id, self.session.user_id, str(self._pid))
        self.unlock()
        return

    async def _value_modify(self, value_name: str):
        if not self.session:
            return
        value_path = self._msg_dir / f"{value_name}.yaml"
        if not value_path.exists():
            await self.send_msg(f"错误: {value_name} 不存在")
            self.unlock()
            return
        async with autoreply_lock:
            self._temp_msg = yaml.safe_load(value_path.read_text(encoding="utf-8"))
            self._temp_msg = modify_msg_data(
                self._temp_msg,
                {
                    "summary": DataVariables(self._sum),
                    "sub_type": DataVariables(self._st),
                },
                ["image"],
                replace=False,
            )
            value_path.write_text(yaml.safe_dump(self._temp_msg))
        await self.send_msg("修改成功")
        self.unlock()

    async def _key(self, key_name: str):
        if not self.session:
            return
        key = key_name
        async with autoreply_lock:
            self._load_rule()
            if key not in self._rule:
                await self.send_msg(f"错误: {key} 不存在")
                self.unlock()
                return
            self._rule[key][0] = self._tm[:]
            self._rule[key][1] = self._d[:]
            self._rule[key][2] = self._m == "contain"
            self._rule[key][3] = self._v[:]
            self._update_rule()
            await self.send_msg("设置成功")
            self.unlock()

    async def roger(self, event: MessageEvent):
        async with self._prod_lock:
            if not self._is_accept_pic:
                return
            if self._l <= 0:
                return
            msg = await dump_message(self.bot, event.get_message())

            def _filter(seg: DumpedSeg) -> bool:
                if seg["type"] != "text" and seg["type"] != "image":
                    return False
                if seg["type"] == "text" and seg["data"].get("text") is None:
                    return False
                if seg["type"] == "image" and seg["data"].get("url") is None:
                    return False
                return True

            msg = msg_filter(_filter, msg)
            url_list = get_multimedias_url(msg, basetypes=["image"])
            for url in url_list:
                await self._urls.put(url)
            self._temp_msg.extend(msg)
            self._l -= 1
            if self._l <= 0:
                value_name = getattr(self, "_value_name", None)
                if value_name is None:
                    raise ValueError
                asyncio.create_task(self.run(Message(f"value --stop {value_name}")))

    async def run(self, args: Message):
        if not self.session:
            return
        new_argv = args.extract_plain_text().strip().split()

        if not await self._legal_case(new_argv):
            if self._argv is None:
                self.unlock()
            return

        if not await self._guard_state(new_argv):
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)
        subcmd = self._parser.subcmd
        if subcmd is None:
            self.unlock()
            return

        if not self._check_perm("autoreplymanager"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        subparser = self._parser.subparsers[subcmd]
        self._k = subparser.opts_value.get("-k", [])
        self._v = subparser.opts_value.get("-v", [])
        if subparser.opts_value.get("--start", [0])[0]:
            self._vstate = "start"
        if subparser.opts_value.get("--stop", [0])[0]:
            self._vstate = "stop"
        _sum = subparser.opts_value.get("--sum", [])
        _st = subparser.opts_value.get("--st", [])
        if _sum or self._vstate != "stop":
            self._sum = _sum
        if _st or self._vstate != "stop":
            self._st = _st
        self._l = subparser.opts_value.get("-l", [1])[0]
        self._d = subparser.opts_value.get("-d", [])
        self._tm = subparser.opts_value.get("--tm", [])
        self._m = subparser.opts_value.get("-m", ["equal"])[0]

        if subcmd == "start":
            await self._start()
            return

        if subcmd == "stop":
            await self._stop()
            return

        if subcmd in ["create", "delete"]:
            await self._create_delete(subcmd)
            return

        if subcmd == "value":
            value_name = subparser.value[0]
            if self._vstate == "start":
                await self._value_start(value_name)
                return
            if self._vstate == "stop":
                await self._value_stop(value_name)
                return
            await self._value_modify(value_name)
            return

        if subcmd == "key":
            key_name = subparser.value[0]
            await self._key(key_name)
            return
