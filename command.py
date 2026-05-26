from __future__ import annotations
from typing import TYPE_CHECKING

import textwrap
import json
import asyncio
import uuid
import httpx
from typing import Any
from pathlib import Path

from nonebot.adapters.onebot.v11 import Bot, MessageSegment, Message
from nonebot.log import logger

from .parser import BotArgParser
from .auxiliaries import rmPath, convertCleanup, sendMsg, stuffDownload
from .tasks import convertPng2V, convertP2Png
from .config import getConfig
config = getConfig()

if TYPE_CHECKING:
    from .session import BotSession

class BotCommand:
    _argv: list[str] | None
    _sentinel = object()
    _name = "otherwise"
    # DON'T FUCKING CALL ME!
    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        if _internal is not self._sentinel: raise TypeError("Please use BotCommand.make() instead of BotCommand()")
        self._bot = bot
        self._session = session
        self._argv = None
        self._parser = self._init_parser()
        self._pid = _pid
        session.commands[_pid] = self

    @classmethod
    def make(cls, bot: Bot, session: BotSession, *, _pid: int | None = None) -> BotCommand | None:
        if _pid is None: _pid = session.curpid
        if session.commands.get(_pid): return None
        return cls(bot, session, _pid=_pid, _internal=cls._sentinel)

    @classmethod
    def getName(cls):
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

    def _init_parser(self):
        return BotArgParser()

    # Judge if the arguments is legal based on the parser and send msg if it's illegal
    async def _legalCase(self, argv: list[str]):
        if self._parser.is_valid(argv): return True

        tip =  "命令格式错误。\n"
        tip += f"输入 /help {self.name} 查看使用方法."
        await self._send_msg(tip)
        return False

    async def _send_msg(self, msg: str | Message):
        if not self.session: return
        await sendMsg(self.bot, self.session.group_id, self.session.user_id, msg)

    # Main function
    async def run(self, args: Message):
        if not self.session:
            self.unlock()
            return
        if not self.session.group_id == "private":
            self.unlock()
            return
        await self._send_msg(f"无效命令，请输入/help获取帮助。")
        self.unlock()

    # Disconnect with the session, you should call in run() before return
    def unlock(self):
        if self._session is None: return
        self._session.commands.pop(self._pid, None)
        self._session.release()
        self._session = None


class BotCommandSession(BotCommand):
    _name = "session"
    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0, need_subcmd=True)
        switch = parser.add_subparser('switch')
        info = parser.add_subparser('info')
        switch.set_rule(min=1, max=1, types=[int])
        info.set_rule(max=0)
        return parser

    async def run(self, args: Message):
        if self.session is None: return

        new_argv = args.extract_plain_text().strip().split()
        if not await self._legalCase(new_argv):
            if self._argv is None: self.unlock()
            return

        if self._argv is not None:
            command = self.session.commands.get(self._pid)
            if not command: return
            tip =  "错误：会话被占用\n"
            tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        subcmd = self._parser.subcmd

        if subcmd == "switch":
            if self._parser.subparsers[subcmd].value is None: return # Also impossible
            pid = self._parser.subparsers[subcmd].value[0]

            if pid <= 0:
                tip =  "错误：pid不合规\n"
                tip += f"pid应大于0。"
                await self._send_msg(tip)
                self.unlock()
                return

            self.session.curpid = pid

        if subcmd == "info":
            commands = self.session.commands
            cmd_info = {pid: cmd.name for pid, cmd in commands.items()}
            tip =  f"前台pid: {self.session.curpid}\n\n"
            tip += f"正在运行的命令: \n{json.dumps(cmd_info, indent=2, ensure_ascii=False)}"
            await self._send_msg(tip)

        self.unlock()


class BotCommandHelp(BotCommand):
    _name = "help"
    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.add_subparser('help')
        parser.add_subparser('session')
        parser.add_subparser('convert')
        parser.add_subparser('randpic')
        parser.add_subparser('shitpost')
        parser.add_subparser('advrandpic')
        return parser

    async def run(self, args: Message):
        if not self.session: return
        new_argv = args.extract_plain_text().strip().split()
        # I know it's impossble to be illegal. Just for formalism :)
        if not await self._legalCase(new_argv):
            if self._argv is None: self.unlock()
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)
        subcmd = self._parser.subcmd

        path = f"file://{config.client_base / "help.png"}"

        if subcmd == "help":
            path = f"file://{config.client_base / "helphelp.png"}"

        if subcmd == "convert":
            path = f"file://{config.client_base / "helpconvert.png"}"

        if subcmd == "randpic":
            path = f"file://{config.client_base / "helprandpic.png"}"

        if subcmd == "advrandpic":
            path = f"file://{config.client_base / "helpadvrandpic.png"}"

        if subcmd == "shitpost":
            path = f"file://{config.client_base / "helpshitpost.png"}"

        if subcmd == "session":
            tip =  "用法: /session <子命令> [参数]\n\n"
            tip += "子命令:\n"
            tip += "  switch <pid>    将前台切换到指定 pid\n"
            tip += "  info            查看当前会话信息\n\n"
            tip += "说明:\n"
            tip += "  支持同时运行多条命令，每条占据一个 pid。\n"
            tip += "  仅前台 pid（curpid）上的命令接收用户输入，\n"
            tip += "  其余 pid 上的命令在后台运行。\n\n"
            tip += "  switch 用于切换前台：\n"
            tip += "  · 切换到空闲 pid 后启动新命令，即可并行执行多个任务\n"
            tip += "  · 切换回某个 pid 即可继续操作该 pid 上的命令\n\n"
            tip += "  新命令启动时自动占用当前 curpid。\n\n"
            tip += "示例:\n"
            tip += "  /session switch 3    将前台切换到 pid=3\n"
            tip += "  /session info        查看所有运行中的命令以及前台对应的pid"
            await self._send_msg(tip)
            self.unlock()
            return

        msg = Message(MessageSegment("image", {"file": path}))

        await self._send_msg(msg)
        self.unlock()


class BotCommandConvert(BotCommand):
    _name = "convert"
    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._runlock = asyncio.Lock()
        self._event = asyncio.Event()
        self._p2png_event = asyncio.Event()
        self._if_accept_pic = False
        self._temp_images: asyncio.Queue[str] = asyncio.Queue()
        self._images : list[str] = []
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
        start = parser.add_subparser('start')
        stop = parser.add_subparser('stop')
        start.set_rule(max=0)
        stop.set_rule(max=0)
        parser.set_rule(max=0, need_subcmd=True)
        return parser

    async def _convertStart(self):
        if not self.session: return
        logger.info(f"用户 {self.session.user_id} 开始了图片收集")
        await self._send_msg("图片收集已开始， Bot 会收集本条信息后你发送的所有图片，直到你发送 /convert stop 完成收集。")
        self._if_accept_pic = True
        asyncio.create_task(convertP2Png(self))
        return

    async def _convertStop(self):
        if not self.session: return
        self._if_accept_pic = False
        user_id = self.session.user_id

        await self._send_msg("保存图片中...")
        async with self.download_lock:
            pass
        self.p2png_event.set()
        async with self.copy_lock:
            pass
        await self._send_msg("保存完毕。")

        images_dir = config.bot_base / self.session.group_id / self.session.user_id / str(self._pid) / "images"
        videos_dir = config.bot_base / self.session.group_id / self.session.user_id / str(self._pid) / "videos"
        await rmPath(videos_dir)
        videos_dir.mkdir(parents=True, exist_ok=True)

        if len(self.images) == 0:
            await convertCleanup(self.session.group_id, self.session.user_id, str(self._pid))
            await self._send_msg("没有有效的图片被保存。")
            self.unlock()
            return

        logger.info(f"用户 {self.session.user_id} 结束收集，共收到 {len(self.images)} 张")

        await self._send_msg(f"有效保存 {len(self.images)} 张图片，开始处理…")

        async def _runTask():
            try:
                await convertPng2V(self.bot, user_id, str(self.pid), images_dir, videos_dir)
            except Exception:
                pass
            finally:
                if self.session: await convertCleanup(self.session.group_id, self.session.user_id, str(self._pid))
                self.unlock()

        asyncio.create_task(_runTask())
        return

    async def run(self, args: Message):
        async with self._runlock:
            if not self.session: return

            new_argv = args.extract_plain_text().strip().split()
            if not await self._legalCase(new_argv):
                if self._argv is None: self.unlock()
                return

            self._parser.parse_argv(new_argv)
            subcmd = self._parser.subcmd

            if self._argv is not None and subcmd == "start":
                command = self.session.commands.get(self._pid)
                if not command: return
                tip =  "错误：会话被占用\n"
                tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
                await self._send_msg(tip)
                return

            if self._argv is None and subcmd == "stop":
                tip =  "错误：会话未开始\n"
                tip += f"你还没有开始收集图片，请先使用 /convert start 。"
                await self._send_msg(tip)
                self.unlock()
                return

            self._argv = new_argv

            if subcmd == "start":
                await self._convertStart()
                return

            if subcmd == "stop":
                await self._convertStop()
                return


class BotCommandRandpic(BotCommand):
    _name = "randpic"
    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0)
        parser.add_opt('-r', required=True, choice=["off", "on"], default=["off"])
        parser.add_opt('-n', required=True, type=int, default=[1])
        return parser

    async def run(self, args: Message):
        if not self.session: return

        new_argv = args.extract_plain_text().strip().split()
        if not await self._legalCase(new_argv):
            if self._argv is None: self.unlock()
            return

        if self._argv is not None:
            command = self.session.commands.get(self._pid)
            if not command: return
            tip =  "错误：会话被占用\n"
            tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)
        if self._parser.opts_value['-r'] is None or self._parser.opts_value['-n'] is None: return # It's impossible, just for type checking
        r18 = self._parser.opts_value['-r'][0]
        num = self._parser.opts_value['-n'][0]

        if num < 1: num = 1
        if num > 10: num = 10

        if r18 == "on" and self.session.group_id != "private":
            tip = "该功能只能在私聊中使用"
            await self._send_msg(tip)
            self.unlock()
            return


        if self.session.group_id not in config.whitelist_groups_setu:
            self.unlock()
            return

        api = "https://manyacg.top/setu"
        if r18 == "on":
            if self.session.user_id not in config.whitelist_users_setu:
                self.unlock()
                return
            api = "https://manyacg.top/sese"
        for i in range(num):
            try:
                msg = Message(MessageSegment("image", {"url": api}))
                msg[0].data["summary"] = "我的新自拍喵[图片]"
                await self._send_msg(msg)
                logger.info(f"发送图片成功")
            except Exception as e:
                logger.error(f"发送图片失败: {e}")
                await self._send_msg(f"图片发送失败：{e}")
        self.unlock()


class BotCommandAdvrandpic(BotCommand):
    _name = "advrandpic"
    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._r18 = 0
        self._num = 1
        self._tag = None
        self._size = "regular"

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0)
        parser.add_opt('-r', required=True, choice=["off", "on", "only"], default=["off"])
        parser.add_opt('-s', required=True, choice=["original", "regular"], default=["regular"])
        parser.add_opt('-t', required=True)
        parser.add_opt('-n', required=True, type=int, default=[1])
        return parser

    async def run(self, args: Message):
        if not self.session: return

        new_argv = args.extract_plain_text().strip().split()
        if not await self._legalCase(new_argv):
            if self._argv is None: self.unlock()
            return

        if self._argv is not None:
            command = self.session.commands.get(self._pid)
            if not command: return
            tip =  "错误：会话被占用\n"
            tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)
        if self._parser.opts_value['-r'] is None or self._parser.opts_value['-s'] is None or self._parser.opts_value['-n'] is None: # It's impossible
            return

        r18 = self._parser.opts_value['-r'][0]
        if r18 != "off" and self.session.group_id != "private":
            tip = "该功能只能在私聊中使用"
            await self._send_msg(tip)
            self.unlock()
            return
        if r18 == "off": self._r18 = 0
        if r18 == "on": self._r18 = 2
        if r18 == "only": self._r18 = 1

        tags = self._parser.opts_value['-t']
        if tags is not None: self._tag =tags[0].split('&')

        self._num = self._parser.opts_value['-n'][0]
        if self._num < 1: self._num = 1
        if self._num > 10: self._num = 10

        self._size = self._parser.opts_value['-s'][0]

        if self.session.group_id not in config.whitelist_groups_setu:
            self.unlock()
            return

        if self._r18 and self.session.user_id not in config.whitelist_users_setu:
            self.unlock()
            return

        api = 'https://api.lolicon.app/setu/v2'
        payload: dict[str, Any] = {
            'r18': self._r18,
            'num': self._num,
            'size': self._size,
        }
        if self._tag is not None: payload['tag'] = self._tag
        headers = {'Content-Type': 'application/json'}

        async with httpx.AsyncClient() as client:
            response = await client.post(api, headers=headers, json=payload)
        if response.status_code != 200:
            logger.error(f"api调用失败，状态码{response.status_code}")
            self.unlock()
            return

        data = response.json()

        if len(data['data']) < self._num:
            await self._send_msg(f"未找到指定数量的图片，仅找到 {len(data['data'])} 张")

        for pic in data['data']:
            try:
                url = pic['urls'][self._size]
                msg = Message(MessageSegment("image", {"url": pic['urls'][self._size]}))
                msg[0].data["summary"] = "我的新自拍喵[图片]"
                await self._send_msg(msg)
                logger.info(f"发送图片成功")
            except Exception as e:
                logger.error(f"发送图片失败: {e}")
                await self._send_msg(f"图片发送失败，大概率要么链接失效要么被河蟹了")

        self.unlock()



class BotCommandShitpost(BotCommand):
    _name = "shitpost"
    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
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

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0, need_subcmd=True)
        start = parser.add_subparser("start")
        stop = parser.add_subparser("stop")
        start.set_rule(min=1, types=[int])
        stop.set_rule(max=0)
        return parser

    async def run(self, args: Message):
        if not self.session: return
        new_argv = args.extract_plain_text().strip().split()
        if not await self._legalCase(new_argv):
            if self._argv is None: self.unlock()
            return

        self._parser.parse_argv(new_argv)
        subcmd = self._parser.subcmd

        if self._argv is not None and subcmd == "start":
            command = self.session.commands.get(self._pid)
            if not command: return
            tip =  "错误：会话被占用\n"
            tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        if self._argv is None and subcmd == "stop":
            tip =  "错误：会话未开始"
            tip += "我还没吃上呢你着急啥，先输入 /shitpost start <群号1> <群号2> ... 开始搬石。"
            await self._send_msg(tip)
            self.unlock()
            return

        self._argv = new_argv

        if subcmd == "start":
            groups = self._parser._subparsers[subcmd].value
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
            return

        if subcmd == "stop":
            self._is_forwardable = False
            await self._send_msg("豪赤，下回要搬的时候记得再叫我。")
            self.unlock()
            return
