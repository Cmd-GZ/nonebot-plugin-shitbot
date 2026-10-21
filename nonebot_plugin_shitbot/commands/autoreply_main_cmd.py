import random
import unicodedata
from typing import Any

import yaml
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent

from ..aux import validate_schema
from ..command import BotCommand
from ..config import config
from ..msgdatabase import BotMsgDataBase
from ..permissions import get_permissions
from ..session import BotSession
from ..tasks import autoreply_lock

_TERM_SCHEMA = {
    "trans": [str],
    "dels": [str],
    "is_contain": bool,
    "keywords": [str],
    "replys": [str],
}


class BotCommandAutoReplyMain(BotCommand):
    _name = "autoreply_main_rec"
    autoreply_dir = config.data / "autoreply"
    setting_path = autoreply_dir / "setting.yaml"
    rule_path = autoreply_dir / "rule.yaml"
    msg_table_path = autoreply_dir / "msg_table.yaml"
    _rule: dict[str, dict[str, Any]]
    _msg_table: dict[str, str]

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    @classmethod
    async def init(cls):
        cls._database = BotMsgDataBase(cls.autoreply_dir)
        cls._rule = {}
        cls._msg_table = {}
        cls.rule_path.touch(exist_ok=True)
        cls.msg_table_path.touch(exist_ok=True)
        default_setting = {
            "is_auto": True,
        }
        if not cls.setting_path.exists():
            cls.setting_path.touch(exist_ok=True)
            cls.setting_path.write_text(
                yaml.safe_dump(default_setting, allow_unicode=True), encoding="utf-8"
            )

    def load_meta(self):
        if (
            not self.rule_path.exists()
            or not self.msg_table_path.exists()
            or not self.setting_path.exists()
        ):
            raise FileNotFoundError
        _rule = yaml.safe_load(self.rule_path.read_text(encoding="utf-8"))
        _msg_table = yaml.safe_load(self.msg_table_path.read_text(encoding="utf-8"))
        if (_rule is not None and not isinstance(_rule, dict)) or (
            _msg_table is not None and not isinstance(_msg_table, dict)
        ):
            raise ValueError
        self._rule = _rule if _rule is not None else {}
        self._msg_table = _msg_table if _msg_table is not None else {}

    async def roger(self, event: MessageEvent):
        group_id = str(getattr(event, "group_id", "private"))
        if event.message_type == "private":
            group_id = "private"
        user_id = str(event.user_id)

        if not get_permissions().check_permission("autoreply", group_id, user_id):
            return

        rule_keys = self._rule.keys()
        raw = event.message.extract_plain_text()

        for key in rule_keys:
            if not validate_schema(self._rule[key], _TERM_SCHEMA):
                continue
            text = raw
            for trans in self._rule[key]["trans"]:
                if trans == "delspace":
                    text = text.replace(" ", "")
                if trans == "delmark":
                    text = "".join(
                        c for c in text if not unicodedata.category(c).startswith("P")
                    )
                if trans == "upper":
                    text = text.upper()
                if trans == "lower":
                    text = text.lower()
            for substr in self._rule[key]["dels"]:
                text = text.replace(substr, "")

            for keyword in self._rule[key]["keywords"]:
                if not (
                    (self._rule[key]["is_contain"] and keyword in text)
                    or (not self._rule[key]["is_contain"] and keyword == text)
                ):
                    continue
                if len(self._rule[key]["replys"]) == 0:
                    continue
                index = random.randint(0, len(self._rule[key]["replys"]) - 1)
                reply = self._rule[key]["replys"][index]
                reply_hash = self._msg_table.get(reply, None)
                if reply_hash is None:
                    continue
                async with autoreply_lock:
                    msg = self._database.prepare_send_msg(reply_hash)
                await self.send_msg(msg, group_id=group_id, user_id=user_id)
                break

    async def run(self, args: Message):
        random.seed()
        async with autoreply_lock:
            await self.init()
            self.load_meta()
