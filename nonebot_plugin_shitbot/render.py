from __future__ import annotations

import asyncio
import base64
import re
import textwrap
from pathlib import Path

import markdown
import nh3
from nonebot.log import logger
from playwright.async_api import Browser, Playwright, async_playwright

from .config import config

_PACKAGE_DIR = Path(__file__).resolve().parent
_KATEX_DIR = _PACKAGE_DIR / "markdown" / "katex"
_CSS_DIR = _PACKAGE_DIR / "markdown" / "css"
_EXTENSIONS = [
    "pymdownx.arithmatex",
    "pymdownx.tasklist",
    "tables",
    "fenced_code",
    "codehilite",
    "pymdownx.tilde",
]
_EXT_CONFIGS = {
    "codehilite": {"guess_lang": False},
    "pymdownx.arithmatex": {"generic": True},
}

_KATEX_SCRIPT = textwrap.dedent(r"""
    renderMathInElement(document.querySelector('.markdown-body'), {
    delimiters: [
        {left: '\\[', right: '\\]', display: true},
        {left: '\\(', right: '\\)', display: false},
    ],
    throwOnError: false,
    });
""")

_IMG_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

_ALLOWED_ROOTS = (_PACKAGE_DIR, config.data, config.cache)

_ALLOWED_TAGS = {
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "span",
    "div",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "a",
    "img",
    "strong",
    "em",
    "del",
    "s",
    "sub",
    "sup",
    "details",
    "summary",
    "kbd",
    "mark",
    "u",
    "ins",
    "dl",
    "dt",
    "dd",
    "input",
}

_ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "code": {"class"},
    "span": {"class"},
    "div": {"class"},
    "pre": {"class"},
    "input": {"type", "checked", "disabled"},
    "th": {"align"},
    "td": {"align"},
    "ul": {"class"},
    "li": {"class"},
    "details": {"open"},
}

_TEMPLATE = textwrap.dedent("""\
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8">
    <style>{css}</style>
    <style>
    .markdown-body {{
        box-sizing: border-box;
        min-width: 200px;
        max-width: 1000px;
        margin: 0 auto;
        padding: 45px;
    }}
    @media (max-width: 767px) {{
        .markdown-body {{ padding: 15px; }}
    }}
    </style>
    </head>
    <body><article class="markdown-body">{body}</article>{extra}</body>
    </html>
""")


class BotMarkdownRender:
    _sentinel = object()
    instance: BotMarkdownRender | None = None

    def __init__(self, *, _internal=None):
        if _internal is not self._sentinel:
            raise ValueError("请使用 MarkdownRender.make() 方法创建实例")
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()
        self._katex_css: str | None = None
        self._katex_jses: dict[str, str] = {}

    @classmethod
    def make(cls) -> BotMarkdownRender:
        if cls.instance is None:
            cls.instance = cls(_internal=cls._sentinel)
        return cls.instance

    async def startup(self):
        async with self._lock:
            if self._browser is not None and self._browser.is_connected():
                return
            if self._pw is not None:
                self._browser = await self._pw.chromium.launch()
                return
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch()

    async def shutdown(self) -> None:
        async with self._lock:
            browser, self._browser = self._browser, None
            pw, self._pw = self._pw, None

            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    logger.debug("浏览器连接已断开，跳过 close")

            if pw is not None:
                try:
                    await pw.stop()
                except Exception:
                    logger.debug("Playwright 驱动已退出，跳过 stop")

    def _get_katex_css(self) -> str:
        def repl(m: re.Match[str]) -> str:
            data = (_KATEX_DIR / "fonts" / m.group(1)).read_bytes()
            return "url(data:font/woff2;base64," + base64.b64encode(data).decode() + ")"

        if self._katex_css is None:
            self._katex_css = (_KATEX_DIR / "katex.min.css").read_text(encoding="utf-8")
            self._katex_css = re.sub(
                r"url\(fonts/([^)]+\.woff2)\)", repl, self._katex_css
            )

        return self._katex_css

    def _load_katex_js(self, name: str) -> str:
        if name not in self._katex_jses:
            self._katex_jses[name] = (_KATEX_DIR / name).read_text(encoding="utf-8")
        return self._katex_jses[name]

    def _get_latex_extra(self, body: str) -> str:
        if "arithmatex" not in body:
            return ""
        return (
            f"<style>{self._get_katex_css()}</style>"
            f"<script>{self._load_katex_js('katex.min.js')}</script>"
            f"<script>{self._load_katex_js('mhchem.min.js')}</script>"
            f"<script>{self._load_katex_js('auto-render.min.js')}</script>"
            f"<script>{_KATEX_SCRIPT}</script>"
        )

    def _process_inline_images(self, html: str) -> str:
        def repl(m: re.Match[str]) -> str:
            src = m.group(2)

            if src.startswith(("http://", "https://", "data:")):
                return m.group(0)

            p = Path(src)
            if not p.is_absolute():
                return m.group(0)

            p = p.resolve()
            if not p.is_file():
                return m.group(0)

            if not any(p.is_relative_to(root.resolve()) for root in _ALLOWED_ROOTS):
                return m.group(0)

            mime = _IMG_MIME.get(p.suffix.lower())
            if mime is None:
                return m.group(0)

            b64 = base64.b64encode(p.read_bytes()).decode()
            return f"{m.group(1)}data:{mime};base64,{b64}{m.group(3)}"

        return re.sub(r'(<img\b[^>]*?\bsrc=")([^"]*)(")', repl, html)

    def _sanitize(self, html: str) -> str:
        return nh3.clean(
            html,
            tags=_ALLOWED_TAGS,
            attributes=_ALLOWED_ATTRS,
            url_schemes={"http", "https", "data"},
        )

    async def _route(self, route) -> None:
        if route.request.resource_type == "image":
            await route.continue_()
        else:
            await route.abort()

    def _to_html(self, md: str, css_path: Path | None = None) -> str:
        body = markdown.markdown(
            md, extensions=_EXTENSIONS, extension_configs=_EXT_CONFIGS
        )
        body = self._sanitize(body)
        body = self._process_inline_images(body)
        css = (css_path or _CSS_DIR / "github-markdown-dark-dimmed.css").read_text(
            encoding="utf-8"
        )
        extra = self._get_latex_extra(body)
        return _TEMPLATE.format(css=css, body=body, extra=extra)

    async def render(
        self,
        md: str,
        *,
        width: int = 900,
        scale: float = 2.0,
        css_path: Path | None = None,
        timeout_ms: int = 30_000,
    ) -> bytes:
        await self.startup()
        if self._pw is None or self._browser is None:
            raise RuntimeError("错误: Playwright 或浏览器未启动")

        html = self._to_html(md, css_path=css_path)
        async with self._lock:
            ctx = await self._browser.new_context(device_scale_factor=scale)
            await ctx.route("**", self._route)
            try:
                page = await ctx.new_page()
                await page.set_viewport_size({"width": width, "height": 10})
                await page.set_content(html, wait_until="load", timeout=timeout_ms)
                png = await page.screenshot(
                    full_page=True, type="png", timeout=timeout_ms
                )
                return png
            finally:
                await ctx.close()
