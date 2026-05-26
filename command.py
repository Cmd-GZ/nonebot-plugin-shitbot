from __future__ import annotations
from typing import TYPE_CHECKING

import requests
import json
import asyncio
import uuid
import httpx
from typing import Dict, List, Any
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
    _argv: List[str] | None
    _sentinel = object()
    _name = "otherwise"
    # DON'T FUCKING CALL ME!
    def __init__(self, bot: Bot, session: BotSession, *, _internal=None):
        if _internal is not self._sentinel: raise TypeError("Please use BotCommand.make() instead of BotCommand()")
        self._bot = bot
        self._session = session
        self._argv = None
        self._parser = self._init_parser()
        session.command = self

    @classmethod
    def make(cls, bot: Bot, session: BotSession) -> BotCommand | None:
        if session.command: return None
        return cls(bot, session, _internal=cls._sentinel)

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

    def _init_parser(self):
        return BotArgParser()

    # Return a list with the truth values of arguments where i-th element is true if and only if the format of arguments conform the i-th expression
    # if necessary, implement it in the subclass like:
    #    return [
    #        <the expression of the first case>,
    #        <the expression of the second case>,
    #        ...
    #    ]
    def _ifLegalGrammars(self, argv: List[str]):
        return [True]

    # Judge if the arugments is legal based on the truthvalues and send msg if it's illegal
    async def _legalCase(self, truthvalues: List[bool]):
        if any(truthvalues): return True

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
        if self.session: self.session.command = None
        self._session = None


class BotCommandHelp(BotCommand):
    _name = "help"
    def __init__(self, bot: Bot, session: BotSession, *, _internal=None):
        super().__init__(bot, session, _internal=_internal)

    def _ifLegalGrammars(self, argv: List[str]):
        return [
            len(argv) == 0, # /help
            len(argv) >= 1 and argv[0] == "help", # /help help ...
            len(argv) >= 1 and argv[0] == "convert", # /help convert ...
            len(argv) >= 1 and argv[0] == "randpic", # /help randpic ...
            len(argv) >= 1 and argv[0] == "advrandpic", # /help advrandpic ...
            len(argv) >= 1 and argv[0] == "shitpost", # /help shitpost ...
            True, # /help ...
        ]

    async def run(self, args: Message):
        if not self.session: return
        new_argv = args.extract_plain_text().strip().split()
        new_truthvalues = self._ifLegalGrammars(new_argv)
        # I know it's impossble to be true. Just for formalism :)
        if not await self._legalCase(new_truthvalues):
            if self._argv is None: self.unlock()
            return

        self._argv = new_argv
        truthvalues = new_truthvalues

        tip =  "使用方法：\n"
        tip += "  /help          显示帮助\n"
        tip += "  /convert       收集图片并批量转换为视频\n"
        tip += "  /randpic       随机发送二次元图片\n"
        tip += "  /advrandpic    随机发送二次元图片，支持指定tag\n"
        tip += "  /shitpost      转发信息到多个群聊中"
        tip += "\n"
        tip += "使用例子：\n"
        tip += "  /help help"

        if truthvalues[1]:
            tip =  "/help:           显示帮助\n\n"
            tip += "命令格式：\n\n"
            tip += "  /help          显示基础帮助\n\n"
            tip += "  /help <命令>   显示<命令>的使用方法\n\n"
            tip += "\n\n"
            tip += "使用例子：\n\n"
            tip += "  /help convert  获取 /convert 命令的使用方法"

        if truthvalues[2]:
            tip =  "/convert:        收集图片并批量转换为视频（仅私聊可用）\n\n"
            tip += "命令格式：\n\n"
            tip += "  /convert start 令 Bot 保存在提示出现后你接下来发送的图片，直至你输入 /convert stop \n\n"
            tip += "  /convert stop  在输入 /convert start 并发送图片后输入， Bot 将停止保存你发送的图片，转而将收集到的图片按顺序转换为视频发送，最后打包发送一个 tar 归档。"

        if truthvalues[3]:
            tip =  "/randpic:        随机发送二次元图片\n\n"
            tip += "命令格式：\n\n"
            tip += "  /randpic unable [数字] 或 /randpic [数字]: 从受限API中随机获取[数字]张二次元图片并发送（不填写默认为1） \n\n"
            tip += "  /randpic able: 作用同上，但图片是从不受限API中获取的（仅私聊可用）"
            tip += "  [数字]的范围是1~10，若输入小于1则会取1，若输入大于10则会取10"

        if truthvalues[4]:
            tip =  "/advrandpic:        随机发送二次元图片\n\n"
            tip += "命令格式：\n\n"
            tip += "  /advrandpic [选项]: 随机获取二次元图片并发送 \n\n"
            tip += "选项：\n\n"
            tip += "    -n <数字>: 设置发送几张图片，范围应在1~10之间，默认为1\n\n"
            tip += "    -r <模式>: 设置是否限制发送图片的类型，默认为off\n\n"
            tip += "        -r off: 仅发送全年龄图片\n\n"
            tip += "        -r on: 不限制发送图片的类型（仅私聊可用）\n\n"
            tip += "        -r only: 仅发送非全年龄图片（仅私聊可用）\n\n"
            tip += "    -s <图片质量>: 设置发送的图片的质量，默认为regular\n\n"
            tip += "        -s regular：发送普通质量的图片\n\n"
            tip += "        -s original：发送原图质量的图片\n\n"
            tip += "    -t <tag表达式>: 发送满足所给的tag表达式的图片，默认为空\n\n"
            tip += "        <仅包含|的子表达式A>|<仅包含|的子表达式B>: 或运算，只要A或B其中一个被满足，该表达式就被满足\n\n"
            tip += "        <子表达式A>&<子表达式B>: 与运算，只有A或B同时被满足，该表达式才被满足\n\n"
            tip += "        |的优先级大于&的优先级\n\n"
            tip += "        tag表达式只能同时包含3个&\n\n"
            tip += "        tag表达式只能同时包含20个|\n\n"
            tip += "        (在表达式中使用括号并不会改变运算优先级，还有可能使表达式无效)\n\n"
            tip += "例子: \n\n"
            tip += "    获取3张original质量的图片: /advrandpic -n 3 -s original\n\n"
            tip += "    获取1张全年龄的图片: /advrandpic -r off -n 1 (或 /advrandpic )\n\n"
            tip += "    获取5张(萝莉或少女)的(白丝或黑丝)的图片: /advrandpic -n 5 -n 萝莉|少女&白丝|黑丝\n\n"

        if truthvalues[5]:
            tip =  "/shitpost:        转发信息到多个群聊中（仅私聊可用）\n\n"
            tip += "命令格式：\n\n"
            tip += "  /convert start <群号1> <群号2> ...:  令 Bot 转发在提示出现后你接下来发送的信息到你指定的群聊，直至你输入 /shitpost stop \n\n"
            tip += "  /shitpost stop  在输入 /shitpost start 后输入， Bot将停止转发你的信息"

        await self._send_msg(tip)
        self.unlock()


class BotCommandConvert(BotCommand):
    _name = "convert"
    def __init__(self, bot: Bot, session: BotSession, *, _internal=None):
        super().__init__(bot, session, _internal=_internal)
        self._runlock = asyncio.Lock()
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

    def _ifLegalGrammars(self, argv: List[str]):
        return [
            len(argv) == 1 and argv[0] == "start", # /convert start
            len(argv) == 1 and argv[0] == "stop", # /convert stop
        ]

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
                await convertPng2V(self.bot, user_id, images_dir, videos_dir)
            except Exception:
                pass
            finally:
                if self.session: await convertCleanup(self.session.group_id, self.session.user_id)
                self.unlock()

        asyncio.create_task(_runTask())
        return

    async def run(self, args: Message):
        async with self._runlock:
            if not self.session: return

            new_argv = args.extract_plain_text().strip().split()
            new_truthvalues = self._ifLegalGrammars(new_argv)
            if not await self._legalCase(new_truthvalues):
                if self._argv is None: self.unlock()
                return

            if self._argv is not None and new_truthvalues[0]:
                if not self.session.command: return
                tip =  "错误：会话被占用\n"
                tip += f"命令 {self.session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
                await self._send_msg(tip)
                return

            if self._argv is None and new_truthvalues[1]:
                tip =  "错误：会话未开始\n"
                tip += f"你还没有开始收集图片，请先使用 /convert start 。"
                await self._send_msg(tip)
                self.unlock()
                return

            # Now there are two cases: self_argv is None and new_truthvalues[0], and self._argv is not None and new_truthvaule[1]
            self._argv = new_argv
            truthvalues = new_truthvalues

            if truthvalues[0]:
                await self._convertStart()
                return

            if truthvalues[1]:
                await self._convertStop()
                return


class BotCommandRandpic(BotCommand):
    _name = "randpic"
    def __init__(self, bot: Bot, session: BotSession, *, _internal=None):
        super().__init__(bot, session, _internal=_internal)

    def _ifLegalGrammars(self, argv: List[str]):
        return [
            len(argv) == 0, # /randpic
            len(argv) == 1 and argv[0].isdigit(), # /randpic <number>
            len(argv) == 1 and argv[0] == "unable", # /randpic unable
            len(argv) == 2 and argv[0] == "unable" and argv[1].isdigit(), # /randpic unable <number>
            len(argv) == 1 and argv[0] == "able", # /randpic able
            len(argv) == 2 and argv[0] == "able" and argv[1].isdigit(), # /randpic able <number>
        ]

    async def run(self, args: Message):
        if not self.session: return

        new_argv = args.extract_plain_text().strip().split()
        new_truthvalues = self._ifLegalGrammars(new_argv)
        if not await self._legalCase(new_truthvalues):
            if self._argv is None: self.unlock()
            return

        if self._argv is not None:
            if not self.session.command: return
            tip =  "错误：会话被占用\n"
            tip += f"命令 {self.session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        truthvalues = new_truthvalues

        num = 1
        if truthvalues[1]: num = int(self._argv[0])
        if truthvalues[3] or truthvalues[5]: num = int(self._argv[1])
        if num < 1: num = 1
        if num > 10: num = 10

        if (truthvalues[4] or truthvalues[5]) and self.session.group_id != "private":
            tip = "该功能只能在私聊中使用"
            await self._send_msg(tip)
            self.unlock()
            return


        if self.session.group_id not in config.whitelist_groups_setu:
            self.unlock()
            return

        if truthvalues[0] or truthvalues[1] or truthvalues[2] or truthvalues[3]:
            api = "https://manyacg.top/setu"
        else:
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
    def __init__(self, bot: Bot, session: BotSession, *, _internal=None):
        super().__init__(bot, session, _internal=_internal)
        self._r18 = 0
        self._num = 1
        self._tag = None
        self._size = "regular"

    def _ifLegalGrammars(self, argv: List[str]):
        def _idx(elem):
            try:
                return argv.index(elem)
            except ValueError:
                return -1
        l = len(argv)
        arg_r = _idx("-r")+1
        arg_n = _idx("-n")+1
        arg_t = _idx("-t")+1
        arg_s = _idx("-s")+1
        temp_truthvalue = [
            l == 0, # /advrandpic
            arg_r > 0 and arg_r < l and argv[arg_r] == "off", # /advrandpic ... -r off ...
            arg_r > 0 and arg_r < l and argv[arg_r] == "on", # /advrandpic ... -r on ...
            arg_r > 0 and arg_r < l and argv[arg_r] == "only", # /advrandpic ... -r only ...
            arg_n > 0 and arg_n < l and argv[arg_n].isdigit(), # /advrandpic ... -n <num> ...
            arg_t > 0 and arg_t < l, # /advrandpic ... -t <tag> ...
            arg_s > 0 and arg_s < l and argv[arg_s] == "regular", # /advrandpic -s regular
            arg_s > 0 and arg_s < l and argv[arg_s] == "original", # /advrandpic -s original
        ]

        and_truthvalue = [
            (
                (arg_n <= 0 or temp_truthvalue[4]) and
                (arg_t <= 0 or temp_truthvalue[5]) and
                (arg_s <= 0 or any(temp_truthvalue[5:7]))
            ), # -r
            (
                (arg_r <= 0 or any(temp_truthvalue[1:4])) and
                (arg_t <= 0 or temp_truthvalue[5]) and
                (arg_s <= 0 or any(temp_truthvalue[5:7]))
            ), # -n
            (
                (arg_r <= 0 or any(temp_truthvalue[1:4])) and
                (arg_n <= 0 or temp_truthvalue[4]) and
                (arg_s <= 0 or any(temp_truthvalue[5:7]))
            ), # -t
            (
                (arg_r <= 0 or any(temp_truthvalue[1:4])) and
                (arg_n <= 0 or temp_truthvalue[4]) and
                (arg_t <= 0 or temp_truthvalue[5])
            ) # -s
        ]
        return [
            temp_truthvalue[0], # /advrandpic
            and_truthvalue[0] and temp_truthvalue[1], # /advrandpic ... -r off ...
            and_truthvalue[0] and temp_truthvalue[2], # /advrandpic ... -r on ...
            and_truthvalue[0] and temp_truthvalue[3], # /advrandpic ... -r only ...
            and_truthvalue[1] and temp_truthvalue[4], # /advrandpic ... -n <num> ...
            and_truthvalue[2] and temp_truthvalue[5], # /advrandpic ... -t <tag> ...
            and_truthvalue[3] and temp_truthvalue[6], # /advrandpic -s regular
            and_truthvalue[3] and temp_truthvalue[7], # /advrandpic -s original
        ]

    async def run(self, args: Message):
        if not self.session: return

        new_argv = args.extract_plain_text().strip().split()
        new_truthvalues = self._ifLegalGrammars(new_argv)
        if not await self._legalCase(new_truthvalues):
            if self._argv is None: self.unlock()
            return

        if self._argv is not None:
            if not self.session.command: return
            tip =  "错误：会话被占用\n"
            tip += f"命令 {self.session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        truthvalues = new_truthvalues

        if (truthvalues[2] or truthvalues[3]) and self.session.group_id != "private":
            tip = "该功能只能在私聊中使用"
            await self._send_msg(tip)
            self.unlock()
            return

        if truthvalues[1]: self._r18 = 0
        if truthvalues[2]: self._r18 = 2
        if truthvalues[3]: self._r18 = 1
        if truthvalues[4]: self._num =int(self._argv[self._argv.index("-n")+1])
        if truthvalues[5]: self._tag =self._argv[self._argv.index("-t")+1].split('&')
        if any([truthvalues[6], truthvalues[7]]): self._size = self._argv[self._argv.index("-s")+1]

        if self._num < 1: self._num = 1
        if self._num > 10: self._num = 10

        if self.session.group_id not in config.whitelist_groups_setu:
            self.unlock()
            return

        if self._r18 and self.session.user_id not in config.whitelist_users_setu:
            self.unlock()
            return

        api = 'https://api.lolicon.app/setu/v2'
        payload: Dict[str, Any] = {
            'r18': self._r18,
            'num': self._num,
            'size': self._size,
        }
        if self._tag is not None: payload['tag'] = self._tag
        headers = {'Content-Type': 'application/json'}

        response = requests.post(api, headers=headers, data=json.dumps(payload))
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
    def __init__(self, bot: Bot, session: BotSession, *, _internal=None):
        super().__init__(bot, session, _internal=_internal)
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

    def _ifLegalGrammars(self, argv: List[str]):
        return [
            len(argv) >= 2 and argv[0] == "start" and all(arg.isdigit() for arg in argv[1:]), # /shitpost start [<group_id>]
            len(argv) == 1 and argv[0] == "stop", # /shitpost stop
        ]

    async def run(self, args: Message):
        if not self.session: return
        new_argv = args.extract_plain_text().strip().split()
        new_truthvalues = self._ifLegalGrammars(new_argv)
        if not await self._legalCase(new_truthvalues):
            if self._argv is None: self.unlock()
            return

        if self._argv is not None and new_truthvalues[0]:
            if not self.session.command: return
            tip =  "错误：会话被占用\n"
            tip += f"命令 {self.session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        if self._argv is None and new_truthvalues[1]:
            tip =  "错误：会话未开始"
            tip += "我还没吃上呢你着急啥，先输入 /shitpost start <群号1> <群号2> ... 开始搬石。"
            await self._send_msg(tip)
            self.unlock()
            return
        # Now there are two cases: self_argv is None and new_truthvalues[0], and self._argv is not None and new_truthvaule[1]
        self._argv = new_argv
        truthvalues = new_truthvalues

        if truthvalues[0]:
            groups = [int(arg) for arg in self._argv[1:]]
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

        if truthvalues[1]:
            self._is_forwardable = False
            await self._send_msg("豪赤，下回要搬的时候记得再叫我。")
            self.unlock()
            return
