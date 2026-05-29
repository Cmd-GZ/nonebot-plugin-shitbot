from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.log import logger

from ..auxs import convert_cleanup, rm_path
from ..command import BotCommand
from ..config import config
from ..parser import BotArgParser
from ..tasks import convert_p_to_png, convert_png_to_v

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandConvert(BotCommand):
    _name = "convert"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._runlock = asyncio.Lock()
        self._event = asyncio.Event()
        self._p2png_event = asyncio.Event()
        self._if_accept_pic = False
        self._temp_images: asyncio.Queue[str] = asyncio.Queue()
        self._images: list[str] = []
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

    def _init_parser(self):
        parser = BotArgParser()
        start = parser.add_subparser("start")
        stop = parser.add_subparser("stop")
        start.set_rule(max=0)
        stop.set_rule(max=0)
        parser.set_rule(max=0, need_subcmd=True)
        return parser

    async def _convert_start(self):
        if not self.session:
            return
        logger.info(f"用户 {self.session.user_id} 开始了图片收集")
        await self._send_msg(
            "图片收集已开始， Bot 会收集本条信息后你发送的所有图片，直到你发送 /convert stop 完成收集。"
        )
        self._if_accept_pic = True
        asyncio.create_task(convert_p_to_png(self))
        return

    async def _convert_stop(self):
        if not self.session:
            return
        self._if_accept_pic = False
        user_id = self.session.user_id

        await self._send_msg("保存图片中...")
        async with self.download_lock:
            pass
        self.p2png_event.set()
        async with self.copy_lock:
            pass
        await self._send_msg("保存完毕。")

        images_dir = (
            config.bot_base
            / self.session.group_id
            / self.session.user_id
            / str(self._pid)
            / "images"
        )
        videos_dir = (
            config.bot_base
            / self.session.group_id
            / self.session.user_id
            / str(self._pid)
            / "videos"
        )
        await rm_path(videos_dir)
        videos_dir.mkdir(parents=True, exist_ok=True)

        if len(self.images) == 0:
            await convert_cleanup(
                self.session.group_id, self.session.user_id, str(self._pid)
            )
            await self._send_msg("没有有效的图片被保存。")
            self.unlock()
            return

        logger.info(
            f"用户 {self.session.user_id} 结束收集，共收到 {len(self.images)} 张"
        )

        await self._send_msg(f"有效保存 {len(self.images)} 张图片，开始处理…")

        async def _run_task():
            try:
                await convert_png_to_v(
                    self.bot, user_id, str(self.pid), images_dir, videos_dir
                )
            except Exception:
                pass
            finally:
                if self.session:
                    await convert_cleanup(
                        self.session.group_id, self.session.user_id, str(self._pid)
                    )
                self.unlock()

        asyncio.create_task(_run_task())
        return

    async def run(self, args: Message):
        async with self._runlock:
            if not self.session:
                return

            new_argv = args.extract_plain_text().strip().split()
            if not await self._legal_case(new_argv):
                if self._argv is None:
                    self.unlock()
                return

            self._parser.parse_argv(new_argv)
            subcmd = self._parser.subcmd

            if self._argv is not None and subcmd == "start":
                command = self.session.commands.get(self._pid)
                if not command:
                    return
                tip = "错误：会话被占用\n"
                tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
                await self._send_msg(tip)
                return

            if self._argv is None and subcmd == "stop":
                tip = "错误：会话未开始\n"
                tip += "你还没有开始收集图片，请先使用 /convert start 。"
                await self._send_msg(tip)
                self.unlock()
                return

            self._argv = new_argv

            if subcmd == "start":
                await self._convert_start()
                return

            if subcmd == "stop":
                await self._convert_stop()
                return
