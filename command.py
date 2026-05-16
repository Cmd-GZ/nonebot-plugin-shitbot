from __future__ import annotations
from typing import TYPE_CHECKING

import asyncio
import shutil
from typing import Dict, List, Optional
from pathlib import Path

from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.log import logger

from .auxiliaries import rmPath, convertCleanup, sendMsg
from .tasks import convertPng2V, convertP2Png
from .config import getConfig
config = getConfig()

if TYPE_CHECKING:
    from .session import BotSession

class BotCommand:
    _sentinel = object()
    # DON'T FUCKING CALL ME!
    def __init__(self, bot: Bot, session: BotSession, args: Message=Message(), *, _internal=None):
        if _internal is not self._sentinel: raise TypeError("Please use BotCommand.make() instead of BotCommand()")
        self._bot = bot
        self._session = session
        self._name = "otherwise"
        self._argv = args.extract_plain_text().strip().split()
        session.command = self

    @classmethod
    def make(cls, bot: Bot, session: BotSession, args: Message=Message()) -> BotCommand | None:
        if session.command: return None
        return cls(bot, session, args, _internal=cls._sentinel)

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

    async def _send_msg(self, msg: str | Message):
        if not self.session: return
        await sendMsg(self.bot, self.session.group_id, self.session.user_id, msg)

    async def setArgv(self, args: Message):
        self._argv = args.extract_plain_text().strip().split()

    async def run(self):
        if not self.session:
            self.unlock()
            return
        if not self.session.group_id == "private":
            self.unlock()
            return
        await self._send_msg(f"无效命令，请输入/help获取帮助。")
        self.unlock()

    def unlock(self):
        if self.session: self.session.command = None
        self._session = None


class BotCommandHelp(BotCommand):
    def __init__(self, bot: Bot, session: BotSession, args: Message=Message(), *, _internal=None):
        super().__init__(bot, session, args, _internal=_internal)
        self._name = "help"

    async def run(self):
        if not self.session:
            self.unlock()
            return
        if not self.session.group_id == "private":
            self.unlock()
            return
        tip =  "使用方法：\n"
        tip += "  /help          显示帮助\n"
        tip += "  /convert       收集图片并批量转换为视频\n"
        tip += "\n"
        tip += "使用例子：\n"
        tip += "  /help help"

        if not self.argv:
            await self._send_msg(tip)
            self.unlock()
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

        await self._send_msg(tip)

        self.unlock()


class BotCommandConvert(BotCommand):
    def __init__(self, bot: Bot, session: BotSession, args: Message=Message(), *, _internal=None):
        super().__init__(bot, session, args, _internal=_internal)
        self._name = "convert"
        self._event = asyncio.Event()
        self._p2png_event = asyncio.Event()
        self._if_accept_pic = False
        self._temp_images: asyncio.Queue[str] = asyncio.Queue()
        self._images : List[str] = []
        self._download_lock: asyncio.Lock = asyncio.Lock()
        self._copy_lock: asyncio.Lock = asyncio.Lock()

    @property
    def p2png_event(self):
        return self._p2png_event

    @property
    def if_accept_pic(self):
        return self._if_accept_pic

    @property
    def temp_images(self):
        return self._temp_images

    @property
    def images(self):
        return self._images

    @property
    def download_lock(self):
        return self._download_lock

    @property
    def copy_lock(self):
        return self._copy_lock

    async def setArgv(self, args: Message):
        if not self.session: return
        new_argv = args.extract_plain_text().strip().split()

        if not new_argv or len(new_argv) != 1 or (new_argv[0] != "start" and new_argv[0] != "stop"):
            tip =  "命令格式错误。\n"
            tip += "输入 /help convert 查看使用方法."
            await self._send_msg(tip)
            return

        if new_argv[0] == "start":
            tip =  "错误：会话被占用\n"
            tip += f"命令 {self.session.command} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        # Now new_argv == ["stop"], and slef.argv == ["start"]
        self._argv = new_argv
        self._event.set()

    async def run(self):
        if not self.session:
            self.unlock()
            return
        if not self.session.group_id == "private":
            self.unlock()
            return

        user_id = int(self.session.user_id)

        if not self.argv or len(self.argv) != 1 or (self.argv[0] != "start" and self.argv[0] != "stop"):
            tip =  "命令格式错误。\n"
            tip += "输入 /help convert 查看使用方法."
            await self._send_msg(tip)
            self.unlock()
            return

        if self.argv[0] == "stop":
            tip =  "错误：会话未开始\n"
            tip += f"你还没有开始收集图片，请先使用 /convert start 。"
            await self._send_msg(tip)
            self.unlock()
            return

        # Now self.argv == ["start"]
        logger.info(f"用户 {self.session.user_id} 开始了图片收集")
        await self._send_msg("图片收集已开始， Bot 会收集本条信息后你发送的所有图片，直到你发送 /convert stop 完成收集。")
        self._if_accept_pic = True
        asyncio.create_task(convertP2Png(self))
        await self._event.wait()
        # Now self.argv == ["stop"]
        self._if_accept_pic = False

        await self._send_msg("下载图片中...")
        async with self.download_lock:
            pass
        await self._send_msg("下载完毕。")

        await self._send_msg("复制图片中...")
        self.p2png_event.set()
        async with self.copy_lock:
            pass
        await self._send_msg("复制完毕。")

        images_dir = config.bot_base / "images" / self.session.user_id
        videos_dir = config.bot_base / "videos" / self.session.user_id
        await rmPath(videos_dir)
        videos_dir.mkdir(parents=True, exist_ok=True)

        if len(self.images) == 0:
            await convertCleanup(self.session.user_id)
            await self._send_msg("没有有效的图片被保存。")
            self.unlock()
            return

        logger.info(f"用户 {self.session.user_id} 结束收集，共收到 {len(self.images)} 张")

        await self._send_msg(f"有效保存 {len(self.images)} 张图片，开始处理…")

        async def _runTask():
            try:
                await convertPng2V(self.bot, str(user_id), images_dir, videos_dir)
            except Exception:
                pass
            finally:
                if self.session: await convertCleanup(self.session.user_id)
                self.unlock()

        asyncio.create_task(_runTask())
        return