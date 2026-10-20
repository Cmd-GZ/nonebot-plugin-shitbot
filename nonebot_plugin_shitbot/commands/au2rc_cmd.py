from __future__ import annotations

import asyncio
import shutil
import uuid
from typing import TYPE_CHECKING

import httpx
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.log import logger

from ..aux import partition_botin_groups, stuff_download
from ..command import BotCommand
from ..config import config
from ..msgutils import (
    dump_message,
    undump_message,
)
from ..parser import BotArgParser

if TYPE_CHECKING:
    from ..session import BotSession

ffmpeg = shutil.which("ffmpeg") or "ffmpeg"


class BotCommandAu2rc(BotCommand):
    _name = "au2rc"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(types=[int])
        return parser

    async def _preprocess_reply(self, args: Message):
        if not self.session:
            return Message()
        if not args or args[0].type != "reply":
            return Message()

        try:
            reply = await self.bot.get_msg(message_id=args[0].data["id"])
        except Exception as e:
            logger.error(f"获取回复消息失败: {e}")
            return Message()
        if reply["message"][0]["type"] not in ["file", "video"]:
            return Message()

        dumped_msg = await dump_message(self.bot, undump_message(reply["message"]))
        dumped_msg[0]["type"] = "record"
        audio_dir = (
            config.cache
            / self.session.group_id
            / self.session.user_id
            / str(self._pid)
            / "audio"
        )
        audio_dir.mkdir(parents=True, exist_ok=True)
        old_path = audio_dir / f"{uuid.uuid4().hex}"
        new_path = audio_dir / f"{uuid.uuid4().hex}.mp3"
        async with httpx.AsyncClient() as client:
            try:
                await stuff_download(client, dumped_msg[0]["data"]["url"], old_path)
            except Exception:
                return Message()
        proc = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-i",
            str(old_path),
            str(new_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await proc.communicate()
            if stdout:
                logger.info(f"ffmpeg stdout:\n{stdout.decode()}")
            if stderr:
                logger.warning(f"ffmpeg stderr:\n{stderr.decode()}")
            if proc.returncode != 0:
                raise Exception(
                    f"(returncode={proc.returncode}): {stderr.decode()[:] if stderr else ''}"
                )
            dumped_msg[0]["data"]["file"] = str(
                config.client_cache / new_path.relative_to(config.cache)
            )
            dumped_msg[0]["data"].pop("url", None)
        except Exception as e:
            logger.error(f"转换失败: {e}")
            return Message()
        return undump_message(dumped_msg)

    async def run(self, args: Message):
        if not self.session:
            return

        new_argv = args.extract_plain_text().strip().split()
        if not await self._legal_case(new_argv):
            if self._argv is None:
                self.unlock()
            return

        if not await self._guard_state():
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        if not self._check_perm("au2rc"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        groups = self._parser.value if self._check_perm("au2rcboardcast") else []
        valid_groups, invalid_groups = await partition_botin_groups(self.bot, groups)
        if invalid_groups:
            await self.send_msg(f"警告: bot不在群组 {invalid_groups} 中")
        if not groups:
            valid_groups = [None]

        if not valid_groups:
            await self.send_msg("错误: 未检测到有效群组")
            self.unlock()
            return
        reply = await self._preprocess_reply(args)
        if not reply:
            await self.send_msg("未检测到有效回复, 请回复一个音频文件后发送命令")
            self.unlock()
            return

        try:
            for group in valid_groups:
                await self.send_msg(reply, group_id=str(group) if group else None)
            if None not in valid_groups:
                await self.send_msg("发送完毕")
        except Exception as e:
            logger.error(f"发送回复消息失败: {e}")
            await self.send_msg("转换失败，请检查文件是否有效")

        self.unlock()
