from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .command import BotCommand


class BotSession:
    _commands: dict[int, BotCommand]
    _objs: dict[str, dict[str, BotSession]] = {}
    _sentinel = object()

    # DON'T FUCKING CALL ME!
    def __init__(self, group_id: str, user_id: str, *, _internal=None):
        if _internal is not self._sentinel:
            raise TypeError("Please use BotSession.make() instead of BotSession()")
        self._commands = {}  # pid > 0: user command; pid = 0: session manager: pid < 0: command-called command
        self._curpid = 1  # So _curpid should be greater than 0
        self._group_id = group_id
        self._user_id = user_id

    def __eq__(self, other):
        if not isinstance(other, BotSession):
            return NotImplemented
        return self.group_id == other.group_id and self.user_id == other.user_id

    @classmethod
    def make(cls, group_id: str, user_id: str) -> BotSession:
        obj = cls.get_obj(group_id, user_id)
        if obj is not None:
            return obj
        cls._objs.setdefault(group_id, {})[user_id] = cls(
            group_id, user_id, _internal=cls._sentinel
        )
        return cls._objs[group_id][user_id]

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
        if pid <= 0:
            return
        self._curpid = pid

    @classmethod
    def get_group_objs(cls, group_id: str) -> list[BotSession]:
        return list(cls._objs.get(group_id, {}).values())

    @classmethod
    def get_obj(cls, group_id: str, user_id: str) -> BotSession | None:
        return cls._objs.get(group_id, {}).get(user_id)

    @classmethod
    def rm_obj(cls, group_id: str, user_id: str) -> None:
        cls._objs.get(group_id, {}).pop(user_id, None)
        if cls._objs.get(group_id) == {}:
            cls._objs.pop(group_id, None)

    def release(self):
        if self._commands == {}:
            BotSession.rm_obj(self.group_id, self.user_id)
