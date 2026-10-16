import asyncio
import math
import random
import time
from pathlib import Path
from typing import Any

import yaml
from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, Message

from ..aux import validate_schema
from ..command import BotCommand
from ..config import config
from ..msgdatabase import BotMsgDataBase
from ..session import BotSession
from ..tasks import shitpost_lock

_SETTING_SCHEMA = {
    "groups": [int],
    "min": int,
    "max": int,
    "is_auto": bool,
}

_META_SCHEMA = {
    "sent": [int],
    "failed": int,
    "timestamp": int,
}

_FRESH_TIME = 60 * 60 * 1

_DEC_COFF = 1.5

_FAILED_LIMIT = 50

_FAILED_COFF = 3.5


class BotCommandShitPostMain(BotCommand):
    _name: str = "shitpost_main_rec"
    shitpost_dir: Path = config.data / "shitpost"
    setting_path: Path = shitpost_dir / "setting.yaml"
    meta_dir: Path = shitpost_dir / "meta"
    _metas: dict[str, Any] = {}
    _database: BotMsgDataBase

    def __init__(
        self, bot: Bot, session: BotSession, *, _pid: int, _internal: Any = None
    ) -> None:
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._setting: dict[str, Any] = {
            "groups": [],
            "min": 60,
            "max": 300,
            "is_auto": False,
        }
        self._exist_groups: list[int] | None = None
        self._sender_tasks: dict[int, asyncio.Task] = {}

    @classmethod
    async def init(cls) -> None:
        cls._database = BotMsgDataBase(cls.shitpost_dir)
        cls.setting_path.touch(exist_ok=True)
        cls.meta_dir.mkdir(exist_ok=True)
        default_setting = {
            "groups": [],
            "min": 60,
            "max": 300,
            "is_auto": False,
        }
        if not cls.setting_path.exists():
            cls.setting_path.write_text(
                yaml.safe_dump(default_setting, allow_unicode=True), encoding="utf-8"
            )

    def load_setting(self) -> None:
        if not self.setting_path.exists():
            raise FileNotFoundError
        _setting = yaml.safe_load(self.setting_path.read_text(encoding="utf-8"))
        if _setting is None:
            _setting = self._setting
        if not validate_schema(_setting, _SETTING_SCHEMA):
            raise ValueError
        if _setting is not None:
            self._setting = _setting
            self.sync_senders()

    def _load_meta(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            _meta = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not validate_schema(_meta, _META_SCHEMA):
                return
            self._metas[path.name] = _meta
        except Exception as e:
            logger.error(f"读取 {path} 失败: {e}")

    def load_metas(self, sha256s: list[str] | None = None) -> None:
        if not self.meta_dir.exists():
            raise FileNotFoundError

        paths = (
            [self.meta_dir / sha256 for sha256 in sha256s]
            if sha256s is not None
            else self.meta_dir.iterdir()
        )
        for path in paths:
            self._load_meta(path)

    def get_msg_hash(self, group_id: int) -> str | None:
        def gumbel() -> float:
            return -math.log(-math.log(random.random()))

        t_now = int(time.time())
        weights = {}
        for key, value in self._metas.items():
            t_stored = value["timestamp"]
            age = t_now - t_stored
            f = value["failed"]
            if f >= _FAILED_LIMIT:
                continue
            if group_id in value["sent"]:
                continue
            weights[key] = (
                _DEC_COFF * math.log(age / _FRESH_TIME + 1)
                + _FAILED_COFF * f
                - gumbel()
            )
        if not weights:
            return None
        return min(weights.keys(), key=lambda k: weights[k])

    async def _sender__send_msg(self, group_id: int) -> None:
        msg_hash = self.get_msg_hash(group_id)
        if msg_hash is None:
            return
        msg = self._database.prepare_send_msg(msg_hash)
        meta_path = self.meta_dir / msg_hash
        try:
            await self.send_msg(msg, group_id=str(group_id), user_id=None)
            self._metas[msg_hash]["sent"].append(group_id)
            self._metas[msg_hash]["failed"] = 0
        except Exception:
            self._metas[msg_hash]["failed"] += 1
        meta_path.write_text(
            yaml.safe_dump(self._metas[msg_hash], allow_unicode=True),
            encoding="utf-8",
        )

    async def _sender(self, group_id: int) -> None:
        while True:
            random_seconds = random.uniform(self._setting["min"], self._setting["max"])
            logger.debug(f"{group_id}: 等待 {random_seconds} 秒")
            await asyncio.sleep(
                random.uniform(self._setting["min"], self._setting["max"])
            )
            if group_id not in self._setting["groups"]:
                break
            async with shitpost_lock:
                await self._sender__send_msg(group_id)

    def sync_senders(self) -> None:
        if self._exist_groups is None:
            return
        for group_id in self._setting["groups"]:
            task = self._sender_tasks.get(group_id)
            if task is None or task.done():
                self._sender_tasks[group_id] = self._create_task(self._sender(group_id))

    async def run(self, args: Message) -> None:
        async with shitpost_lock:
            await self.init()
            self.load_setting()
            self.load_metas()
        self._exist_groups = list(
            set(group["group_id"] for group in await self.bot.get_group_list())
        )
        for group in list(set(self._setting["groups"])):
            if all(group != exist_group for exist_group in self._exist_groups):
                logger.warning(f"bot不在 {group} 中")
                self._setting["groups"].remove(group)
        self.sync_senders()
