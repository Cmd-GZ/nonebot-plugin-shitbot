from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nonebot import require
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from PIL import Image

require("nonebot_plugin_htmlrender")
from nonebot_plugin_htmlrender import md_to_pic

from ..command import BotCommand
from ..parser import BotArgParser

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandMd2pic(BotCommand):
    _name = "md2pic"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._md = ""
        self._scale = 2
        self._css = ""
        self._padding = 30
        self._min_w = 20
        self._max_w = 2000
        self._min_h = 20
        self._max_h = None

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
        parser.add_opt("--max_h", required=True, type=int, default=[])

        return parser

    async def _render(self) -> bytes:

        min_w = int(self._scale * self._min_w)
        max_w = self._max_w
        min_h = int(self._scale * self._min_h)
        max_h = (
            int(self._scale * self._max_h) if self._max_h is not None else self._max_h
        )
        padding = int(self._scale * self._padding)

        raw = await md_to_pic(
            self._md, width=max_w, css_path=self._css, device_scale_factor=self._scale
        )
        img = Image.open(io.BytesIO(raw))

        # Get the background color (the upper-left color)
        bgpx: Any = img.getpixel((0, 0))
        bgr, bgg, bgb = int(bgpx[0]), int(bgpx[1]), int(bgpx[2])

        def is_bg(r: int, g: int, b: int, *, delta: int = 6) -> bool:
            return (
                abs(r - bgr) < delta and abs(g - bgg) < delta and abs(b - bgb) < delta
            )

        def is_column_has_content(x: int):
            for y in range(0, h, 4):
                pixel: Any = img.getpixel((x, y))
                r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
                if not is_bg(r, g, b):
                    return True
            return False

        def is_row_has_content(y: int):
            for x in range(0, w, 4):
                pixel: Any = img.getpixel((x, y))
                r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
                if not is_bg(r, g, b):
                    return True
            return False

        w, h = img.size
        content_left, content_right = 0, w
        content_top, content_bottom = 0, h

        # Find out the leftmost column that has content
        for x in range(w):
            if is_column_has_content(x):
                content_left = x
                break

        # Find out the rightmost column that has content
        for x in range(w - 1, content_left - 1, -1):
            if is_column_has_content(x):
                content_right = x + 1
                break

        # Find out the top row that has content
        for y in range(h):
            if is_row_has_content(y):
                content_top = y
                break

        # Find out the bottom row that has content
        for y in range(h - 1, content_top - 1, -1):
            if is_row_has_content(y):
                content_bottom = y + 1
                break

        crop_left = max(0, content_left - padding)
        crop_right = max(crop_left + min_w + 1, content_right + padding)
        crop_top = max(0, content_top - padding)
        crop_bottom = max(crop_top + min_h + 1, content_bottom + padding)
        if max_h is not None:
            crop_bottom = min(crop_bottom, crop_top + max_h)

        crop_right = min(crop_right, w)
        crop_bottom = min(crop_bottom, h)
        img = img.crop((crop_left, crop_top, crop_right, crop_bottom))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

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

        if not await self._guard_state():
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        if self._pid >= 0 and not self._check_perm("md2pic"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        self._scale = self._parser.opts_value["-s"][0]
        theme = self._parser.opts_value["-t"][0]
        self._css = str(Path(__file__).resolve().parent.parent / "css" / f"{theme}.css")
        self._padding = self._parser.opts_value["--padding"][0]
        self._min_w = self._parser.opts_value["--min_w"][0]
        self._max_w = self._parser.opts_value["--max_w"][0]
        self._min_h = self._parser.opts_value["--min_h"][0]
        self._max_h = (
            self._parser.opts_value["--max_h"][0]
            if len(self._parser.opts_value["--max_h"]) > 0
            else None
        )
        self._md = self._parser.value[0]

        self._padding = max(0, self._padding)
        self._padding = min(50, self._padding)
        self._max_w = min(10000000, self._max_w)
        self._max_w = max(0, self._max_w)
        self._min_w = min(self._max_w, self._min_w)
        self._min_w = max(0, self._min_w)
        if self._max_h is not None:
            self._max_h = min(10000000, self._max_h)
            self._max_h = max(0, self._max_h)
            self._min_h = min(self._max_h, self._min_h)
        self._min_h = max(0, self._min_h)

        img = await self._render()

        msg = Message(MessageSegment.image(img))
        await self.send_msg(msg)

        self.unlock()
