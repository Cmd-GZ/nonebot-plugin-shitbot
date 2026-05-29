from __future__ import annotations

import asyncio
import json
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger

from .auxiliaries import (
    convert_cleanup,
    md_to_pic_auto_size,
    rm_path,
    send_msg,
)
from .config import config
from .parser import BotArgParser
from .tasks import convert_p_to_png, convert_png_to_v


if TYPE_CHECKING:
    from .session import BotSession


class BotCommand:
    _argv: list[str] | None
    _sentinel = object()
    _name = "otherwise"

    # DON'T FUCKING CALL ME!
    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        if _internal is not self._sentinel:
            raise TypeError("Please use BotCommand.make() instead of BotCommand()")
        self._bot = bot
        self._session = session
        self._argv = None
        self._parser = self._init_parser()
        self._pid = _pid
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

    def _init_parser(self):
        return BotArgParser()

    async def _send_format_error(self):
        tip = "命令格式错误。\n"
        tip += f"输入 /help {self.name} 查看使用方法."
        await self._send_msg(tip)

    # Judge if the arguments is legal based on the parser and send msg if it's illegal
    async def _legal_case(self, argv: list[str]):
        if self._parser.is_valid(argv):
            return True
        await self._send_format_error()
        return False

    async def _send_msg(self, msg: str | Message):
        if not self.session:
            return
        await send_msg(self.bot, self.session.group_id, self.session.user_id, msg)

    # Main function
    async def run(self, args: Message):
        if not self.session:
            self.unlock()
            return
        if not self.session.group_id == "private":
            self.unlock()
            return
        await self._send_msg("无效命令，请输入/help获取帮助。")
        self.unlock()

    # Disconnect with the session, you should call in run() before return
    def unlock(self):
        if self._session is None:
            return
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
        switch = parser.add_subparser("switch")
        info = parser.add_subparser("info")
        switch.set_rule(min=1, max=1, types=[int])
        info.set_rule(max=0)
        return parser

    async def run(self, args: Message):
        if self.session is None:
            return

        new_argv = args.extract_plain_text().strip().split()
        if not await self._legal_case(new_argv):
            if self._argv is None:
                self.unlock()
            return

        if self._argv is not None:
            command = self.session.commands.get(self._pid)
            if not command:
                return
            tip = "错误：会话被占用\n"
            tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        subcmd = self._parser.subcmd

        if subcmd == "switch":
            if self._parser.subparsers[subcmd].value is None:
                return  # Also impossible
            pid = self._parser.subparsers[subcmd].value[0]

            if pid <= 0:
                tip = "错误：pid不合规\n"
                tip += "pid应大于0。"
                await self._send_msg(tip)
                self.unlock()
                return

            self.session.curpid = pid
            await self._send_msg(f"已将前台pid设为 {pid}")
            if len(self.session.commands.keys()) <= 1:
                await self._send_msg(
                    "警告：当前无其它命令正在运行，该设置会随着用户会话被释放而被重置。"
                )

        if subcmd == "info":
            commands = self.session.commands
            cmd_info = {pid: cmd.name for pid, cmd in commands.items()}
            tip = f"前台pid: {self.session.curpid}\n\n"
            tip += f"正在运行的命令: \n{json.dumps(cmd_info, indent=2, ensure_ascii=False)}"
            await self._send_msg(tip)

        self.unlock()


class BotCommandHelp(BotCommand):
    _name = "help"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.add_subparser("help")
        parser.add_subparser("session")
        parser.add_subparser("convert")
        parser.add_subparser("randpic")
        parser.add_subparser("shitpost")
        parser.add_subparser("advrandpic")
        parser.add_subparser("md2pic")
        return parser

    async def run(self, args: Message):
        if not self.session:
            return
        new_argv = args.extract_plain_text().strip().split()
        # I know it's impossble to be illegal. Just for formalism :)
        if not await self._legal_case(new_argv):
            if self._argv is None:
                self.unlock()
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)
        subcmd = self._parser.subcmd

        tip = textwrap.dedent("""\
            ```bash
            可用命令：
            /sesssion    管理当前会话
            /help        显示帮助信息
            /convert     收集图片并批量转换为视频（仅私聊）
            /randpic     随机获取二次元图片
            /advrandpic  随机获取二次元图片，支持指定标签
            /shitpost    将消息转发到多个群聊（仅私聊）
            /md2pic      将markdown文本转换为图片输出

            示例：
            /help help     查看 /help 的用法
            ```
        """)

        if subcmd == "help":
            tip = textwrap.dedent("""\
                ```bash
                /help: 显示帮助信息

                使用方式：
                /help          显示基础帮助
                /help <命令>   显示指定命令的详细用法

                示例：
                /help          显示命令列表
                /help convert  查看 /convert 的用法
                ```
            """)

        if subcmd == "convert":
            tip = textwrap.dedent("""\
                ```bash
                /convert: 收集图片并批量转换为视频

                使用方式：
                /convert start  开始收集图片
                                之后你发送的所有图片都会被 Bot 保存

                /convert stop   停止收集，将图片转为视频并打包发送

                示例：
                /convert start
                (发送图片...)
                /convert stop

                注意：此命令仅限私聊使用
                ```
            """)

        if subcmd == "randpic":
            tip = textwrap.dedent("""\
                ```bash
                /randpic: 随机获取二次元图片并发送

                使用方式：
                /randpic [选项]

                选项：
                -n <数字>   设置发送图片数量，范围 1~10，默认为 1
                -r <模式>   内容模式，默认为 off
                    off: 启用内容过滤
                    on:  关闭内容过滤 [仅私聊可用]

                示例：
                /randpic         获取 1 张图片
                /randpic -n 3    获取 3 张图片

                注意：-r on 仅限私聊使用
                ```
            """)

        if subcmd == "advrandpic":
            tip = textwrap.dedent("""\
                ```bash
                /advrandpic: 随机获取二次元图片，支持标签筛选

                使用方式：
                /advrandpic [选项]

                选项：
                -n <数字>       设置发送图片数量，范围 1~10，默认为 1
                -r <模式>       内容模式，默认为 off
                    off:  启用内容过滤
                    on:   关闭内容过滤 [仅私聊可用]
                    only: 仅发送被过滤的内容 [仅私聊可用]
                -s <质量>       图片质量，默认为 regular
                    regular:  普通质量
                    original: 原图质量
                -t <表达式>     标签筛选表达式，默认为空（不筛选）

                tag表达式写法：
                | 表示"或"：萝莉|少女 → 有萝莉或少女的标签就行
                & 表示"与"：白丝&黑丝 → 同时有白丝和黑丝的标签才行

                混合使用时，| 优先结合：萝莉|少女&白丝|黑丝
                → 先处理 | 得到 (萝莉|少女) 和 (白丝|黑丝)
                → 再用 & 连接，相当于 (萝莉|少女) 且 (白丝|黑丝)
                → 最终效果：有(萝莉或少女) 且 有(白丝或黑丝)

                限制：最多 3 个 &，最多 20 个 |
                ！请勿使用括号，不会改变优先级，还可能让表达式无效

                例子：
                /advrandpic                   获取 1 张图片
                /advrandpic -n 3 -s original  获取 3 张原图
                /advrandpic -n 5 -t 萝莉|少女&白丝|黑丝
                    获取 (萝莉 或 少女) 且 (白丝 或 黑丝) 的图片，共 5 张

                注意：-r on 和 -r only 仅限私聊使用
                ```
            """)

        if subcmd == "shitpost":
            tip = textwrap.dedent("""\
                ```bash
                /shitpost: 将消息转发到多个群聊

                使用方式：
                /shitpost start <群号1> [群号2] [群号3] ...
                    开始转发，之后你发送的所有消息都会转发到指定群

                /shitpost stop
                    停止转发

                示例：
                /shitpost start 123456 789012
                (发送消息...)
                /shitpost stop

                注意：此命令仅限私聊使用
                - 至少需要指定 1 个群号
                - Bot 必须已经在目标群中
                - 支持文本、图片、视频消息以及合并转发消息
                ```
            """)

        if subcmd == "session":
            tip = textwrap.dedent("""\
                ```bash
                用法: /session <子命令> [参数]

                子命令:
                    switch <pid>    将前台切换到指定 pid
                    info            查看当前会话信息

                说明:
                    支持同时运行多条命令，每条占据一个 pid。
                    仅前台 pid（curpid）上的命令接收用户输入，
                    其余 pid 上的命令在后台运行。

                    switch 用于切换前台：
                    · 切换到空闲 pid 后启动新命令，即可并行执行多个任务
                    · 切换回某个 pid 即可继续操作该 pid 上的命令

                    新命令启动时自动占用当前 curpid

                    若会话中无任何命令在运行，会话的释放会丢失当前的设置。

                示例:
                    /session switch 3    将前台切换到 pid=3
                    /session info        查看所有运行中的命令以及前台对应的pid
                ```
            """)

        if subcmd == "md2pic":
            tip = textwrap.dedent("""\
                ```bash
                用法: /md2pic < -c > [选项] (换行)
                        <markdown文本>

                选项:
                    -c: 占位符, 用于分割参数项与Markdown正文, 为必填项
                    -s <倍率>: 设置缩放倍率, 可填小数, 数值越大生成的图片越清晰, 数值应在0~50之间, 默认为2
                    -t <渲染主题>: 指定渲染主题, 默认为 github-markdown-dark-dimmed
                    --padding <留空像素>: 设置渲染结果四周留空的宽度像素, 默认为 30
                    --min_w <宽度像素>: 设置最小宽度像素, 默认为 20
                    --max_w <宽度像素>: 设置最大宽度像素, 该值会影响Markdown排版, 默认为 2000
                    --min_h <高度像素>: 设置最小高度像素, 默认为 20
                    --max_h <高度像素>: 设置最大宽度像素, 默认为 无限
                注意: --padding, --min_w, --max_w, --min_h, max_h 均只能填入正整数
                示例1: 按默认参数输出Markdown文本
                    /md2pic -c
                    # Title
                    Hello World
                ```
                # Title
                Hello World
                ```bash
                示例2: 按缩放倍率 5.14, 用 github-markdown-dark-dimmed 主题输出行间公式
                    /md2pic -s 5.14 -c -t github-markdown-dark-dimmed
                    $$
                    天^{-1}\\in\\R\\\\
                    \\text{属实逆天}
                    $$
                ```
                $$
                天^{-1}\\in\\R\\\\
                \\text{属实逆天}
                $$
            """)

        img = await md_to_pic_auto_size(
            tip,
            css_path=str(
                Path(__file__).resolve().parent
                / "css"
                / "github-markdown-dark-dimmed.css"
            ),
        )
        msg = Message(MessageSegment.image(img))

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


class BotCommandRandpic(BotCommand):
    _name = "randpic"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0)
        parser.add_opt("-r", required=True, choice=["off", "on"], default=["off"])
        parser.add_opt("-n", required=True, type=int, default=[1])
        return parser

    async def run(self, args: Message):
        if not self.session:
            return

        new_argv = args.extract_plain_text().strip().split()
        if not await self._legal_case(new_argv):
            if self._argv is None:
                self.unlock()
            return

        if self._argv is not None:
            command = self.session.commands.get(self._pid)
            if not command:
                return
            tip = "错误：会话被占用\n"
            tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)
        if (
            self._parser.opts_value["-r"] is None
            or self._parser.opts_value["-n"] is None
        ):
            return  # It's impossible, just for type checking
        r18 = self._parser.opts_value["-r"][0]
        num = self._parser.opts_value["-n"][0]

        num = max(num, 1)
        num = min(num, 10)

        if self.session.group_id != "private":
            num = 1

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
                logger.info("发送图片成功")
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
        parser.add_opt(
            "-r", required=True, choice=["off", "on", "only"], default=["off"]
        )
        parser.add_opt(
            "-s", required=True, choice=["original", "regular"], default=["regular"]
        )
        parser.add_opt("-t", required=True)
        parser.add_opt("-n", required=True, type=int, default=[1])
        return parser

    async def run(self, args: Message):
        if not self.session:
            return

        new_argv = args.extract_plain_text().strip().split()
        if not await self._legal_case(new_argv):
            if self._argv is None:
                self.unlock()
            return

        if self._argv is not None:
            command = self.session.commands.get(self._pid)
            if not command:
                return
            tip = "错误：会话被占用\n"
            tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)
        if (
            self._parser.opts_value["-r"] is None
            or self._parser.opts_value["-s"] is None
            or self._parser.opts_value["-n"] is None
        ):  # It's impossible
            return

        r18 = self._parser.opts_value["-r"][0]
        if r18 != "off" and self.session.group_id != "private":
            tip = "该功能只能在私聊中使用"
            await self._send_msg(tip)
            self.unlock()
            return
        if r18 == "off":
            self._r18 = 0
        if r18 == "on":
            self._r18 = 2
        if r18 == "only":
            self._r18 = 1

        tags = self._parser.opts_value["-t"]
        if tags is not None:
            self._tag = tags[0].split("&")

        self._num = self._parser.opts_value["-n"][0]
        self._num = max(self._num, 1)
        self._num = min(self._num, 10)
        if self.session.group_id != "private":
            self._num = 1

        self._size = self._parser.opts_value["-s"][0]

        if self.session.group_id not in config.whitelist_groups_setu:
            self.unlock()
            return

        if self._r18 and self.session.user_id not in config.whitelist_users_setu:
            self.unlock()
            return

        api = "https://api.lolicon.app/setu/v2"
        payload: dict[str, Any] = {
            "r18": self._r18,
            "num": self._num,
            "size": self._size,
        }
        if self._tag is not None:
            payload["tag"] = self._tag
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient() as client:
            response = await client.post(api, headers=headers, json=payload)
        if response.status_code != 200:
            logger.error(f"api调用失败，状态码{response.status_code}")
            self.unlock()
            return

        data = response.json()

        if len(data["data"]) < self._num:
            await self._send_msg(f"未找到指定数量的图片，仅找到 {len(data['data'])} 张")

        for pic in data["data"]:
            pid = str(pic["pid"])
            title = pic["title"]
            author = pic["author"]
            url = pic["urls"][self._size]
            text = f"标题: {title}\n作者: {author}\nPID:  {pid}"
            try:
                msg = Message(
                    [
                        MessageSegment("text", {"text": text}),
                        MessageSegment("image", {"url": url}),
                    ]
                )
                msg[0].data["summary"] = "我的新自拍喵[图片]"
                await self._send_msg(msg)
                logger.info("发送图片成功")
            except Exception as e:
                logger.error(f"发送图片失败: {e}")
                text += f"\n图片发送失败, 大概率被河蟹了, 请尝试私聊使用该命令\n{e}"
                await self._send_msg(text)

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
            tip = "错误：会话未开始"
            tip += "我还没吃上呢你着急啥，先输入 /shitpost start <群号1> <群号2> ... 开始搬石。"
            await self._send_msg(tip)
            self.unlock()
            return

        self._argv = new_argv

        if subcmd == "start":
            groups = self._parser._subparsers[subcmd].value
            exist_groups = await self.bot.get_group_list()
            for group in groups:
                if all(
                    group != exist_group["group_id"] for exist_group in exist_groups
                ):
                    tip = "错误：存在未知群号\n"
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


class BotCommandMd2pic(BotCommand):
    _name = "md2pic"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(min=1, max=1)
        parser.add_opt("-c", necessary=True)
        parser.add_opt("-s", required=True, type=float, default=[2])
        parser.add_opt(
            "-t",
            required=True,
            choice=["github-markdown-dark-dimmed"],
            default=["github-markdown-dark-dimmed"],
        )
        parser.add_opt("--padding", required=True, type=int, default=[30])
        parser.add_opt("--min_w", required=True, type=int, default=[20])
        parser.add_opt("--max_w", required=True, type=int, default=[2000])
        parser.add_opt("--min_h", required=True, type=int, default=[20])
        parser.add_opt("--max_h", required=True, type=int, default=None)

        return parser

    async def run(self, args: Message):
        if not self.session:
            return
        new_argss = args.extract_plain_text().split("\n", 1)
        if len(new_argss) < 2:
            await self._send_format_error()
            if self._argv is None:
                self.unlock()
            return
        new_argv = new_argss[0].strip().split()
        new_argv.append(new_argss[1])
        if not await self._legal_case(new_argv):
            if self._argv is None:
                self.unlock()
            return

        if self._argv is not None:
            command = self.session.commands.get(self._pid)
            if not command:
                return
            tip = "错误：会话被占用\n"
            tip += f"命令 {command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
            await self._send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        scale = self._parser.opts_value["-s"][0]  # type: ignore[index]
        theme = self._parser.opts_value["-t"][0]  # type: ignore[index]
        side_padding = self._parser.opts_value["--padding"][0]  # type: ignore[index]
        min_w = self._parser.opts_value["--min_w"][0]  # type: ignore[index]
        max_w = self._parser.opts_value["--max_w"][0]  # type: ignore[index]
        min_h = self._parser.opts_value["--min_h"][0]  # type: ignore[index]
        max_h = (
            self._parser.opts_value["--max_h"][0]
            if self._parser.opts_value["--max_h"] is not None
            else None
        )
        md = self._parser.value[0]

        side_padding = max(0, side_padding)
        side_padding = min(50, side_padding)
        max_w = min(10000000, max_w)
        max_w = max(0, max_w)
        min_w = min(max_w, min_w)
        min_w = max(0, min_w)
        if max_h is not None:
            max_h = min(10000000, max_h)
            max_h = max(0, max_h)
            min_h = min(max_h, min_h)
        min_h = max(0, min_h)

        img = await md_to_pic_auto_size(
            md,
            device_scale_factor=scale,
            css_path=str(Path(__file__).resolve().parent / "css" / f"{theme}.css"),
            side_padding=side_padding,
            min_w=min_w,
            max_w=max_w,
            min_h=min_h,
            max_h=max_h,
        )

        msg = Message(MessageSegment.image(img))
        await self._send_msg(msg)

        self.unlock()
