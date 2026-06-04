from __future__ import annotations

import re
from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger
from pixivpy_async import AppPixivAPI
from pixivpy_async.utils import JsonDict

from ..command import BotCommand
from ..config import config
from ..parser import BotArgParser

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandPixiv(BotCommand):
    _name = "pixiv"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._r18 = 0
        self._size = "large"
        self._picid = -1

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(min=1, max=1, types=[int])
        parser.add_opt("-r", required=True, choice=["off", "on"], default=["off"])
        parser.add_opt(
            "-s", required=True, choice=["regular", "original"], default=["regular"]
        )
        return parser

    @staticmethod
    async def _login() -> AppPixivAPI:
        client = AppPixivAPI(bypass=True)
        await client.login(refresh_token=config.pixiv_access_token)
        return client

    def _get_image_url(self, illust: JsonDict) -> list[str]:
        urls = []
        prefix = "https://i.pixiv.re/img-master"
        suffix = "_master1200.jpg"
        if self._size == "original":
            prefix = "https://i.pixiv.re/img-original"
            suffix = ".jpg"
        if illust.page_count is None:
            return urls
        if illust.page_count > 1:
            if illust.meta_pages is None:
                return urls
            for page in illust.meta_pages:
                url = page.image_urls.get("original")
                if url:
                    urls.append(
                        re.sub(r"^.*?(?=/img/)", prefix, url, count=1).replace(
                            ".jpg", suffix
                        )
                    )
            return urls

        if illust.meta_single_page is None:
            return urls
        url = illust.meta_single_page.original_image_url
        urls.append(
            re.sub(r"^.*?(?=/img/)", prefix, url, count=1).replace(".jpg", suffix)
        )
        return urls

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
            await self.send_msg(tip)
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        r18 = self._parser.opts_value["-r"][0]

        self._r18 = 1 if r18 == "on" else 0

        if not self._check_perm("pixiv"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        if self._r18 and not self._check_perm("nsfw"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        self._size = self._parser.opts_value["-s"][0]
        self._picid = self._parser.value[0]
        await self.send_msg("开始获取图片...")
        api = None
        try:
            api = await self._login()
            res = await api.illust_detail(self._picid)
            illust = res.illust
            if illust is None:
                raise ValueError("未找到该图片")
            if self._r18 < illust.x_restrict:
                raise ValueError("该图片包含成人内容")

            title = illust.title
            author = illust.user.name
            urls = self._get_image_url(illust)
            print(urls)
            if not urls:
                raise ValueError("未找到该图片的元数据")
            msgs = [Message()]
            msg = msgs[0]
            msg.append(
                MessageSegment("text", {"text": f"标题: {title}\n作者: {author}\n"})
            )
            count = 0
            for url in urls:
                seg = MessageSegment("image", {"url": url})
                seg.data["summary"] = "我的新自拍喵[图片]"
                msg.append(seg)
                count += 1
                if count == 10:
                    msgs.append(Message())
                    msg = msgs[-1]
                    count = 0
            for msg in msgs:
                await self.send_msg(msg)
            logger.info("发送图片成功")
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            await self.send_msg(f"图片发送失败：{e}")
        if api is not None and api.session is not None:
            await api.session.close()
        self.unlock()
