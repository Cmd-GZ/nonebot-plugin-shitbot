from __future__ import annotations
from typing import TYPE_CHECKING

import asyncio
import shutil
import uuid
import httpx
from typing import Dict, List, Optional
from pathlib import Path

from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.log import logger

from .auxiliaries import rmPath, convertCleanup, sendMsg, stuffDownload
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
        if not self.session: return
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
        if not self.session: return
        tip =  "使用方法：\n"
        tip += "  /help          显示帮助\n"
        tip += "  /convert       收集图片并批量转换为视频\n"
        tip += "  /randpic       随机发送二次元图片\n"
        tip += "  /shitpost      转发信息到多个群聊中"
        tip += "\n"
        tip += "使用例子：\n"
        tip += "  /help help"

        if not self.argv:
            await self._send_msg(tip)
            self.unlock()
            return

        if self.argv[0] == "help":
            tip =  "/help:           显示帮助\n\n"
            tip += "命令格式：\n\n"
            tip += "  /help          显示基础帮助\n\n"
            tip += "  /help <命令>   显示<命令>的使用方法\n\n"
            tip += "\n\n"
            tip += "使用例子：\n\n"
            tip += "  /help convert  获取 /convert 命令的使用方法"

        if self.argv[0] == "convert":
            tip =  "/convert:        收集图片并批量转换为视频（仅私聊可用）\n\n"
            tip += "命令格式：\n\n"
            tip += "  /convert start 令 Bot 保存在提示出现后你接下来发送的图片，直至你输入 /convert stop \n\n"
            tip += "  /convert stop  在输入 /convert start 并发送图片后输入， Bot 将停止保存你发送的图片，转而将收集到的图片按顺序转换为视频发送，最后打包发送一个 tar 归档。"

        if self.argv[0] == "randpic":
            tip =  "/randpic:        随机发送二次元图片\n\n"
            tip += "命令格式：\n\n"
            tip += "  /randpic unable 或 /randpic: 从受限API中随机获取一张二次元图片并发送 \n\n"
            tip += "  /randpic able stop: 从不受限API中随机获取一张二次元图片并发送（仅私聊可用）"

        if self.argv[0] == "shitpost":
            tip =  "/shitpost:        转发信息到多个群聊中（仅私聊可用）\n\n"
            tip += "命令格式：\n\n"
            tip += "  /convert start <群号1> <群号2> ...:  令 Bot 转发在提示出现后你接下来发送的信息到你指定的群聊，直至你输入 /shitpost stop \n\n"
            tip += "  /shitpost stop  在输入 /shitpost start 后输入， Bot将停止转发你的信息"

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
            if not self.session.command: return
            tip =  "错误：会话被占用\n"
            tip += f"命令 {self.session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        # Now new_argv == ["stop"], and slef.argv == ["start"]
        self._argv = new_argv
        self._event.set()

    async def run(self):
        if not self.session: return
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

        images_dir = config.bot_base / self.session.group_id / self.session.user_id / "images"
        videos_dir = config.bot_base / self.session.group_id / self.session.user_id / "videos"
        await rmPath(videos_dir)
        videos_dir.mkdir(parents=True, exist_ok=True)

        if len(self.images) == 0:
            await convertCleanup(self.session.group_id, self.session.user_id)
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
                if self.session: await convertCleanup(self.session.group_id, self.session.user_id)
                self.unlock()

        asyncio.create_task(_runTask())
        return


class BotCommandRandpic(BotCommand):
    def __init__(self, bot: Bot, session: BotSession, args: Message=Message(), *, _internal=None):
        super().__init__(bot, session, args, _internal=_internal)
        self._name = "randpic"

    async def run(self):
        if not self.session: return
        if len(self.argv) >= 2 or (len(self.argv) >= 1 and self.argv[0] not in ["able", "unable"]):
            tip =  "命令格式错误。\n"
            tip += "输入 /help randpic 查看使用方法."
            await self._send_msg(tip)
            self.unlock()
            return

        if len(self.argv) >= 1 and self.argv[0] == "able" and self.session.group_id != "private":
            tip = "该功能只能在私聊中使用"
            await self._send_msg(tip)
            self.unlock()
            return


        if self.session.group_id not in config.whitelist_groups_setu:
            self.unlock()
            return

        if not self.argv or len(self.argv) == 0 or (len(self.argv) >=1 and self.argv[0] == "unable"):
            api = "https://manyacg.top/setu"
        else:
            if self.session.user_id not in config.whitelist_users_setu:
                self.unlock()
                return
            api = "https://manyacg.top/sese"

        images_dir = config.bot_base / self.session.group_id / self.session.user_id / "images"
        await rmPath(images_dir)
        images_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}"
        save_path = images_dir / safe_name

        async with httpx.AsyncClient() as client:
            try:
                await stuffDownload(client, api, save_path)
                logger.info(f"下载图片成功: {save_path}")
            except Exception as e:
                logger.error(f"下载图片失败 {api}: {e}")

        try:
            client_path = config.client_base / save_path.relative_to(config.bot_base)
            await self._send_msg(Message(MessageSegment.image(f"file://{client_path}")))
            logger.info(f"发送图片成功: {client_path}")
        except Exception as e:
            logger.error(f"发送 {save_path.name} 失败: {e}")
            await self._send_msg(f"图片发送失败：{e}")

        await rmPath(images_dir)
        self.unlock()


class BotCommandShitpost(BotCommand):
    def __init__(self, bot: Bot, session: BotSession, args: Message=Message(), *, _internal=None):
        super().__init__(bot, session, args, _internal=_internal)
        self._name = "shitpost"
        self._is_forwardable = False
        self._groups = []
        self._event = asyncio.Event()

    @property
    def is_forwardable(self):
        return self._is_forwardable

    @property
    def groups(self):
        return self._groups

    @property
    def event(self):
        return self._event

    async def setArgv(self, args: Message):
        if not self.session: return
        new_argv = args.extract_plain_text().strip().split()

        if not new_argv or len(new_argv) == 0 or new_argv[0] not in ["start", "stop"] or (new_argv[0] == "start" and len(new_argv) <= 1) or (new_argv[0] == "start" and any(not arg.isdigit() for arg in new_argv[1:])):
            tip =  "命令格式错误。\n"
            tip += "输入 /help shitpost 查看使用方法。"
            await self._send_msg(tip)
            return


        if new_argv[0] == "start":
            if not self.session.command: return
            tip =  "错误：会话被占用\n"
            tip += f"命令 {self.session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        self._event.set()

    async def run(self):
        if not self.session: return

        if not self.argv or len(self.argv) == 0 or self.argv[0] not in ["start", "stop"] or (self.argv[0] == "start" and len(self.argv) <= 1) or (self.argv[0] == "start" and any(not arg.isdigit() for arg in self.argv[1:])):
            tip =  "命令格式错误。\n"
            tip += "输入 /help shitpost 查看使用方法。"
            await self._send_msg(tip)
            self.unlock()
            return

        if self.argv[0] == "stop":
            tip =  "错误：会话未开始"
            tip += "我还没吃上呢你着急啥，先输入 /shitpost start [群号] 开始搬石。"
            await self._send_msg(tip)
            self.unlock()
            return

        groups = [int(arg) for arg in self.argv[1:]]
        exist_groups = await self.bot.get_group_list()
        for group in groups:
            if all(group != exist_group['group_id'] for exist_group in exist_groups):
                tip =  "错误：存在未知群号\n"
                tip += f"Bot 未在 {group} 中，请检查输入是否正确。"
                await self._send_msg(tip)
                self.unlock()
                return

        self._groups = groups
        self._is_forwardable = True
        await self._send_msg("消息转发已开启，请将你要搬的史发给我。")
        await self.event.wait()

        self._is_forwardable = False
        await self._send_msg("豪赤，下回要搬的时候记得再叫我。")
        self.unlock()
        return
