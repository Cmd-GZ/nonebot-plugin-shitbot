from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.log import logger

from ..aux import get_forward_nodes, send_msg
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
        self._event = asyncio.Event()
        self._shitlock = asyncio.Lock()

    @property
    def is_forwardable(self):
        return self._is_forwardable

    @property
    def groups(self):
        return self._groups

    @property
    def event(self):
        return self._event

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0, need_subcmd=True)
        start = parser.add_subparser("start")
        stop = parser.add_subparser("stop")
        start.set_rule(min=1, types=[int])
        stop.set_rule(max=0)
        return parser

    async def roger(self, event: MessageEvent):
        msg = event.get_message()

        if not self._is_forwardable:
            return

        async def _send(group: int, msg: Message, maxtry: int):
            for i in range(maxtry):
                try:
                    if not msg:
                        return
                    message = msg
                    if msg[0].type == "forward":
                        msg_id = msg[0].data.get("id")
                        if msg_id is None:
                            return
                        forward_data = await self.bot.get_forward_msg(id=msg_id)
                        forward_msgs = forward_data.get("messages", [])
                        message = get_forward_nodes(
                            forward_msgs, config.max_message_depth, summary="喵~"
                        )
                    else:
                        for seg in message:
                            seg.data["summary"] = "喵~"
                            if seg.data.get("sub_type", 0) != 0:
                                seg.data["sub_type"] = 1
                        message[-1].data["summary"] = "喵~"
                    await send_msg(bot=self.bot, group_id=group, msg=message)
                    return
                except Exception as e:
                    if i >= maxtry - 1:
                        logger.error(f"转发失败:{e}")
                        return
                    logger.error(f"转发失败，准备第{i + 1}次重试")
                    await asyncio.sleep(0.25)

        async with self._shitlock:
            for group in self.groups:
                asyncio.create_task(_send(group, msg, 3))
            await asyncio.sleep(random.randint(30, 120))

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
