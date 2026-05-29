from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot, Message

from ..command import BotCommand
from ..parser import BotArgParser
from .md2pic_cmd import BotCommandMd2pic

if TYPE_CHECKING:
    from ..session import BotSession


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

        _pid = -1
        pids = self.session.commands.keys()
        while _pid in pids:
            _pid -= 1
        md2pic = BotCommandMd2pic.make(self.bot, self.session, _pid=_pid)
        tip = "-c\n" + tip
        msg = Message(tip)
        await md2pic.run(msg)  # type: ignore
        self.unlock()
