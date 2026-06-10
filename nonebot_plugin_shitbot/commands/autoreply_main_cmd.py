from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING, Any

import yaml
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent

from ..aux import validate_schema
from ..command import BotCommand
from ..config import config
from ..msgutils import MSG_SCHEMA, DumpedSeg, msg_map, undump_message
from ..tasks import autoreply_lock

if TYPE_CHECKING:
    from ..session import BotSession


_LIST_SCHEMA = [[str], [str], bool, [str], None]


# Simple auto reply, reconstructing.
class BotCommandAutoReplyMain(BotCommand):
    _name = "autoreply_main"
    _autoreply_dir = config.data / "autoreply"
    _rule_path = _autoreply_dir / "rule.yaml"
    _msg_dir = _autoreply_dir / "messages"
    _image_dir = _autoreply_dir / "images"
    _contain_image_dir = config.client_base / _image_dir.relative_to(config.bot_base)
    _rule: dict[str, list[Any]]

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._rule = {}

    def load_rule(self):
        _rule = yaml.safe_load(self._rule_path.read_text(encoding="utf-8"))
        if _rule is not None and not isinstance(_rule, dict):
            raise ValueError
        self._rule = _rule if _rule is not None else {}

    async def roger(self, event: MessageEvent):
        group_id = str(getattr(event, "group_id", "private"))
        if event.message_type == "private":
            group_id = "private"
        user_id = str(event.user_id)

        rule_keys = self._rule.keys()
        raw = event.get_message().extract_plain_text()

        for key in rule_keys:
            if len(self._rule[key]) < 4 or not validate_schema(
                self._rule[key], _LIST_SCHEMA
            ):
                continue
            text = raw
            for trans in self._rule[key][0]:
                if trans == "delspace":
                    text = text.replace(" ", "")
                if trans == "delmarks":
                    text = re.sub(r"[^\w\s]", "", text)
                if trans == "uppercase":
                    text = text.upper()
                if trans == "lowercase":
                    text = text.lower()
            for substr in self._rule[key][1]:
                text = text.replace(substr, "")
            if not (
                (self._rule[key][2] and key in text)
                or (not self._rule[key][2] and key == text)
            ):
                continue
            if len(self._rule[key][3]) == 0:
                continue
            index = random.randint(0, len(self._rule[key][3]) - 1)
            msg_name = self._rule[key][3][index]
            msg_path = self._msg_dir / f"{msg_name}.yaml"
            if not msg_path.exists():
                continue
            dumped_msg = yaml.safe_load(msg_path.read_text(encoding="utf-8"))
            if not validate_schema(dumped_msg, MSG_SCHEMA):
                continue

            def _map(seg: DumpedSeg) -> DumpedSeg:
                if seg["type"] != "image":
                    return seg
                seg["data"]["file"] = (
                    f"file://{self._contain_image_dir / seg['data']['file']!s}"
                )
                return seg

            dumped_msg = msg_map(_map, dumped_msg)

            msg = undump_message(dumped_msg)
            await self.send_msg(msg, group_id=group_id, user_id=user_id)
            return

    async def run(self, args: Message):
        async with autoreply_lock:
            self._autoreply_dir.mkdir(exist_ok=True, parents=True)
            self._image_dir.mkdir(exist_ok=True)
            self._msg_dir.mkdir(exist_ok=True)
            self._rule_path.touch(exist_ok=True)
            self.load_rule()
