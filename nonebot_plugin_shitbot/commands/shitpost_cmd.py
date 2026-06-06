from __future__ import annotations

import asyncio
import random
import uuid
import httpx
from typing import TYPE_CHECKING, Any

from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment, MessageEvent
from nonebot.log import logger

from ..aux import get_forward_nodes, send_msg, message_to_list, get_multimedias_url, stuff_download
from ..command import BotCommand
from ..config import config
from ..parser import BotArgParser

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandShitpost(BotCommand):
    _name = "shitpost"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._is_forwardable = False
        self._groups = []
        self._prod_lock = asyncio.Lock()
        self._shitlock = asyncio.Lock()

    @property
    def is_forwardable(self):
        return self._is_forwardable

    @property
    def groups(self):
        return self._groups

    @staticmethod
    def _msg_url_to_file(msg: list[dict[str, Any]], paths: list[str], depth: int):
        for seg in msg:
            if paths == []:
                continue
            if seg["type"] in ["image", "video", "file"]:
                data = {"file": f"file://{paths.pop(0)}", "summary": "喵~"}
                seg["data"] = data
                continue
            if depth <= 0:
                continue
            if seg["type"] == "forward" or seg["type"] == "node":
                msgs = seg["data"].get("content")
                BotCommandShitpost._msg_url_to_file(msgs, paths, depth - 1)
                continue

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0, need_subcmd=True)
        start = parser.add_subparser("start")
        stop = parser.add_subparser("stop")
        start.set_rule(min=1, types=[int])
        stop.set_rule(max=0)
        return parser

    async def roger(self, event: MessageEvent):
        if not self._is_forwardable:
            return
        if self.session is None:
            return
        msg = event.get_message()
        async with self._prod_lock:
            msg_list = await message_to_list(self.bot, msg)
            urls = get_multimedias_url(msg_list, config.max_message_depth)
            medias = []
            medias_path = []
            media_dir = config.cache / self.session.group_id / self.session.user_id / str(self._pid) / "medias"
            media_dir.mkdir(parents=True, exist_ok=True)
            for url in urls:
                media_path = media_dir / f"{uuid.uuid4().hex}"
                async with httpx.AsyncClient() as client:
                    await stuff_download(client, url, media_path)
                    container_path = config.client_base / media_path.relative_to(
                        config.bot_base
                    )
                    medias_path.append(media_path)
                    medias.append(str(container_path))

        self._msg_url_to_file(msg_list, medias, config.max_message_depth)
        if msg_list == []:
            return
        if len(msg_list) == 1 and msg_list[0]["type"] == "forward":
            msg = msg_list[0]["data"].get("content")
        else:
            msg = Message(MessageSegment(seg["type"], seg["data"]) for seg in msg_list)
        async with self._shitlock:
            for group in self._groups:
                await self.send_msg(msg, group_id=group)
            for path in medias_path:
                path.unlink()
            rand = random.randint(60, 300)
            logger.info(f"等待 {rand} 秒后再次发送")
            await asyncio.sleep(rand)

    async def run(self, args: Message):
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
            await self.send_msg(tip)
            return

        if self._argv is None and subcmd == "stop":
            tip = "错误：会话未开始"
            tip += "我还没吃上呢你着急啥，先输入 /shitpost start <群号1> <群号2> ... 开始搬石。"
            await self.send_msg(tip)
            self.unlock()
            return

        self._argv = new_argv

        if not self._check_perm("shitpost"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        if subcmd == "start":
            groups = self._parser._subparsers[subcmd].value
            exist_groups = await self.bot.get_group_list()
            for group in groups:
                if all(
                    group != exist_group["group_id"] for exist_group in exist_groups
                ):
                    tip = "错误：存在未知群号\n"
                    tip += f"Bot 未在 {group} 中，请检查输入是否正确。"
                    await self.send_msg(tip)
                    self.unlock()
                    return

            self._groups = groups
            self._is_forwardable = True
            await self.send_msg("消息转发已开启，请将你要搬的史发给我。")
            return

        if subcmd == "stop":
            self._is_forwardable = False
            await self.send_msg("豪赤，下回要搬的时候记得再叫我。")
            self.unlock()
            return
