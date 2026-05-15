from __future__ import annotations
from typing import TYPE_CHECKING

import asyncio


if TYPE_CHECKING:
    from .command import BotCommand

class BotSession:
    _command: BotCommand | None
    _objs: dict[tuple[str, str], BotSession] = {}
    _sentinel = object()
    # DON'T FUCKING CALL ME!
    def __init__(self, group_id: str, user_id: str, *, _internal=None):
        if _internal is not self._sentinel: raise TypeError("Please use BotSession.make() instead of BotSession()")
        self._group_id = group_id
        self._user_id = user_id
        self._command = None

    def __eq__(self, other):
        if not isinstance(other, BotSession): return NotImplemented
        return self.group_id == other.group_id and self.user_id == other.user_id

    def __hash__(self):
        return hash((self.group_id, self.user_id))

    @classmethod
    def make(cls, group_id: str, user_id: str):
        obj = cls._objs.get((group_id, user_id))
        if obj: return obj
        return cls(group_id, user_id, _internal=cls._sentinel)

    @property
    def group_id(self) -> str:
        return self._group_id

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def command(self) -> BotCommand | None:
        return self._command

    @command.setter
    def command(self, command: BotCommand | None) -> None:
        self._command = command

    @classmethod
    def getObj(cls, group_id: str, user_id: str) -> BotSession | None:
        return cls._objs.get((group_id, user_id))

    @classmethod
    def rmObj(cls, group_id: str, user_id: str) -> None:
        cls._objs.pop((group_id, user_id), None)