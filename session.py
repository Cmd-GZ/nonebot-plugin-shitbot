from __future__ import annotations
from typing import TYPE_CHECKING

import asyncio


if TYPE_CHECKING:
    from .command import BotCommand

class BotSession:
    _commands: dict[int, BotCommand]
    _objs: dict[tuple[str, str], BotSession] = {}
    _sentinel = object()
    # DON'T FUCKING CALL ME!
    def __init__(self, group_id: str, user_id: str, *, _internal=None):
        if _internal is not self._sentinel: raise TypeError("Please use BotSession.make() instead of BotSession()")
        self._commands = {} # pid > 0: user command; pid = 0: session manager: pid < 0: command-called command
        self._curpid = 1 # So _curpid should be greater than 0
        self._group_id = group_id
        self._user_id = user_id

    def __eq__(self, other):
        if not isinstance(other, BotSession): return NotImplemented
        return self.group_id == other.group_id and self.user_id == other.user_id

    @classmethod
    def make(cls, group_id: str, user_id: str) -> BotSession:
        key = (group_id, user_id)
        obj = cls._objs.get(key)
        if obj: return obj
        cls._objs[key] = cls(group_id, user_id, _internal=cls._sentinel)
        return cls._objs[key]

    @property
    def group_id(self) -> str:
        return self._group_id

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def commands(self) -> dict[int, BotCommand]:
        return self._commands

    @property
    def curpid(self) -> int:
        return self._curpid

    @curpid.setter
    def curpid(self, pid: int):
        if pid <= 0: return
        self._curpid = pid

    @classmethod
    def getObj(cls, group_id: str, user_id: str) -> BotSession | None:
        return cls._objs.get((group_id, user_id))

    @classmethod
    def rmObj(cls, group_id: str, user_id: str) -> None:
        cls._objs.pop((group_id, user_id), None)

    def release(self):
        if self._commands == {}: BotSession.rmObj(self.group_id, self.user_id)