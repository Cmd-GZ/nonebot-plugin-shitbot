from __future__ import annotations
from typing import TYPE_CHECKING

import asyncio


if TYPE_CHECKING:
    from .session import BotSession

class BotCommand:
    _sentinel = object()

    def __init__(self, session: BotSession, *, _internal=None):
        if _internal is not self._sentinel: raise TypeError("Please use BotCommand.make() instead of BotCommand()")
        self._name = "otherwise"
        self._session = session
        session.command = self

    @classmethod
    def make(cls, session: BotSession):
        if session.command: return None
        return cls(session, _internal=cls._sentinel)

    @property
    def session(self):
        return self._session

    @property
    def name(self):
        return self._name

    @session.setter
    def session(self, session: BotSession | None):
        self._session = session

    def run(self):
        print("Error: Illegal command. Running /help to learn more.")
        self.unlock()

    def unlock(self):
        if self.session: self._session.command = None
        self.session = None

class BotCommandHelp(BotCommand):
    def __init__(self, session: BotSession, argv):
        super().__init__(session)
        self._name = "help"
        self._argv = argv

    @property
    def argv(self):
        return self._argv

    def run(self):
        tips = "help"
        if len(self.argv) == 1 or len(self.argv) >= 3:
            print(tips)
            return
        if self.argv[1] == "help": tips = "help help"
        if self.argv[1] == "convert": tips = "help convert"
        print(tips)
        self.unlock()
