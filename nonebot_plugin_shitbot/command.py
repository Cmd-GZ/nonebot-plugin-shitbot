from __future__ import annotations

import asyncio
from functools import wraps
from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent

from .aux import rm_path
from .config import config
from .msgutils import send_msg
from .parser import BotArgParser
from .permissions import permissions

if TYPE_CHECKING:
    from .session import BotSession


def _cancellable_run(func):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        task = asyncio.current_task()
        if task is not None:
            self._run_tasks.add(task)
        try:
            return await func(self, *args, **kwargs)
        except asyncio.CancelledError:
            pass
        finally:
            if task is not None:
                self._run_tasks.discard(task)

    return wrapper


def _cancellable_roger(func):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        task = asyncio.current_task()
        if task is not None:
            self._roger_tasks.add(task)
        try:
            return await func(self, *args, **kwargs)
        except asyncio.CancelledError:
            pass
        finally:
            if task is not None:
                self._roger_tasks.discard(task)

    return wrapper


# Base class of all the commands
class BotCommand:
    # class fields:
    #    _name: command name
    #    _sentinel: used to prevent from calling __init__ directly
    # fields:
    #    _bot: bot
    #    _session: the command's session
    #    _argv: current arguments of the command, which is also represented as the command's state
    #    _parser: arguments parser used to parse arguments
    #    _pid: command's id in its session
    _argv: list[str] | None
    _sentinel = object()
    _name = "otherwise"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "run" in cls.__dict__:
            cls.run = _cancellable_run(cls.run)
        if "roger" in cls.__dict__:
            cls.roger = _cancellable_roger(cls.roger)

    # Use make() instead of this
    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        if _internal is not self._sentinel:
            raise TypeError("Please use BotCommand.make() instead of BotCommand()")
        self._bot = bot
        self._session = session
        self._argv = None
        self._parser = self._init_parser()
        self._pid = _pid
        self._run_tasks: set[asyncio.Task] = set()
        self._roger_tasks: set[asyncio.Task] = set()
        self._inner_tasks: set[asyncio.Task] = set()
        self._inner_cmds: list[BotCommand] = []
        session.commands[_pid] = self

    @classmethod
    def make(
        cls, bot: Bot, session: BotSession, *, _pid: int | None = None
    ) -> BotCommand | None:
        if _pid is None:
            _pid = session.curpid
        if session.commands.get(_pid):
            return None
        return cls(bot, session, _pid=_pid, _internal=cls._sentinel)

    @classmethod
    def get_name(cls):
        return cls._name

    @property
    def bot(self):
        return self._bot

    @property
    def session(self):
        return self._session

    @property
    def name(self):
        return self._name

    @property
    def argv(self):
        return self._argv

    @property
    def pid(self):
        return self._pid

    @property
    def run_tasks(self):
        return self._run_tasks

    @property
    def roger_tasks(self):
        return self._roger_tasks

    def _init_parser(self):
        return BotArgParser()

    async def _send_format_error(self):
        tip = f"命令格式错误:\n{self._parser.err}\n"
        tip += f"输入 /help {self.name} 查看使用方法."
        await self.send_msg(tip)

    # Judge if the arguments are legal based on the parser and send msg if it's illegal
    async def _legal_case(self, argv: list[str]):
        if self._parser.is_valid(argv):
            return True
        await self._send_format_error()
        return False

    async def _guard_state(self):
        if self._argv is not None:
            if (
                self._session is None
                or (command := self._session.commands.get(self._pid)) is None
            ):
                return False
            tip = "错误：会话被占用\n"
            tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self.send_msg(tip)
            return False
        return True

    async def send_msg(
        self,
        msg: str | Message,
        *,
        group_id: str | None = None,
        user_id: str | None = None,
    ):
        if not self.session:
            return
        gid, uid = group_id, user_id
        if gid is None:
            gid = self.session.group_id
        if uid is None:
            uid = self.session.user_id
        if gid == "public":
            return
        if gid == "private":
            gid = None
            uid = int(uid)
        else:
            gid = int(gid)
            uid = None
        await send_msg(bot=self.bot, group_id=gid, user_id=uid, msg=msg)

    def _check_perm(self, entry_name: str):
        if not self.session:
            return False
        return permissions.check_permission(
            entry_name, self.session.group_id, self.session.user_id
        )

    def _create_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._inner_tasks.add(task)
        task.add_done_callback(self._inner_tasks.discard)
        return task

    def _rm_cache(self):
        if not self.session:
            return
        cache_path = (
            config.cache / self.session.group_id / self.session.user_id / str(self._pid)
        )
        rm_path(cache_path)

    async def roger(self, event: MessageEvent):
        pass

    # Main function
    async def run(self, args: Message):
        if not self.session:
            self.unlock()
            return
        if not self._check_perm("otherwise"):
            self.unlock()
            return
        await self.send_msg("无效命令，请输入/help获取帮助。")
        self.unlock()

    # Disconnect with the session, you should call in run() before return
    def unlock(self):
        if self._session is None:
            return
        for task in self._inner_tasks:
            if not task.done():
                task.cancel()
        for cmd in self._inner_cmds:
            cmd.unlock()
        self._rm_cache()
        self._session.commands.pop(self._pid, None)
        self._session.release()
        self._session = None


BotCommand.run = _cancellable_run(BotCommand.run)
BotCommand.roger = _cancellable_roger(BotCommand.roger)
