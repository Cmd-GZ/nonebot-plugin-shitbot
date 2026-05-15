from __future__ import annotations
from typing import TYPE_CHECKING

import asyncio

from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.log import logger

if TYPE_CHECKING:
    from .session import BotSession

class BotCommand:
    _sentinel = object()

    def __init__(self, session: BotSession, args: Message=Message(), *, _internal=None):
        if _internal is not self._sentinel: raise TypeError("Please use BotCommand.make() instead of BotCommand()")
        self._session = session
        self._name = "otherwise"
        self._argv = args.extract_plain_text().strip().split()
        session.command = self

    @classmethod
    def make(cls, session: BotSession, args: Message=Message()):
        if session.command: return None
        return cls(session, args, _internal=cls._sentinel)

    @property
    def session(self):
        return self._session

    @property
    def name(self):
        return self._name

    @property
    def argv(self):
        return self._argv

    @session.setter
    def session(self, session: BotSession | None):
        self._session = session

    @argv.setter
    def argv(self, args: Message = CommandArg()):
        self._argv = args.extract_plain_text().strip().split()

    async def run(self, bot: Bot):
        if not self.session: return
        if not self.session.group_id == "private": return
        user_id = int(self.session.user_id)
        await bot.send_private_msg(user_id=user_id, message=f"无效命令，请输入/help获取帮助。")
        self.unlock()

    def unlock(self):
        if self.session: self.session.command = None
        self.session = None

class BotCommandHelp(BotCommand):
    def __init__(self, session: BotSession):
        super().__init__(session)
        self._name = "help"

    async def run(self, bot: Bot):
        if not self.session: return
        if not self.session.group_id == "private": return
        user_id = int(self.session.user_id)
        tip =  "使用方法：\n"
        tip += "  /help          显示帮助\n"
        tip += "  /convert       收集图片并批量转换为视频\n"
        tip += "\n"
        tip += "使用例子：\n"
        tip += "  /help help"

        if not self.argv:
            await bot.send_private_msg(user_id=user_id, message=tip)
            return

        if self.argv[0] == "help":
            tip =  "/help:           显示帮助\n"
            tip += "命令格式：\n"
            tip += "  /help          显示基础帮助\n"
            tip += "  /help <命令>   显示<命令>的使用方法\n"
            tip += "\n"
            tip += "使用例子：\n"
            tip += "  /help convert  获取 /convert 命令的使用方法"

        if self.argv[0] == "convert":
            tip =  "/convert:        收集图片并批量转换为视频\n"
            tip += "命令格式：\n"
            tip += "  /convert start 令 Bot 保存在提示出现后你接下来发送的图片，直至你输入 /convert stop \n"
            tip += "  /convert stop  在输入 /convert start 并发送图片后输入， Bot 将停止保存你发送的图片，转而将收集到的图片按顺序转换为视频发送，最后打包发送一个 tar 归档。"

        await bot.send_private_msg(user_id=user_id, message=tip)

        self.unlock()
