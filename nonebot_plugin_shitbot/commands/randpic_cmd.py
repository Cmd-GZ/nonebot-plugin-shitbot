from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

import httpx
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger

from ..command import BotCommand
from ..config import config
from ..msgutils import dump_message, get_downloaded_msg
from ..parser import BotArgParser

if TYPE_CHECKING:
    from ..session import BotSession


class BotCommandRandpic(BotCommand):
    _name = "randpic"
    _apis = [
        "https://api.manyacg.top/v1/artwork/random",
        "https://api.lolicon.app/setu/v2",
    ]

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._api = ""
        self._r18 = 0
        self._num = 1
        self._keyword = ""
        self._size = "regular"

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(max=0)
        parser.add_opt(
            "-a",
            required=True,
            choice=["1", "2", "m", "l", "manyacg", "lolicon", "r"],
            default=["r"],
        )
        parser.add_opt(
            "-r", required=True, choice=["off", "on", "only"], default=["off"]
        )
        parser.add_opt(
            "-s", required=True, choice=["original", "regular"], default=["regular"]
        )
        parser.add_opt("-n", required=True, type=int, default=[1])
        parser.add_opt("-k", required=True, type=str, default=[""])
        return parser

    async def _get_pics(self) -> list[dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "r18": self._r18,
        }

        if self._api == self._apis[0]:
            payload["limit"] = self._num
            keyword = self._keyword.replace("|", ",").replace("&", "|")
            if keyword != "":
                payload["keyword"] = keyword

        elif self._api == self._apis[1]:
            payload["num"] = self._num
            payload["size"] = self._size
            if self._keyword:
                tag = self._keyword.split("&")
                payload["tag"] = tag

        async with httpx.AsyncClient(timeout=30.0) as client:
            response_code = -1
            response = None
            try:
                response = await client.post(self._api, headers=headers, json=payload)
                response_code = response.status_code
            except Exception as e:
                logger.error(f"获取图片失败: {e}")
                return []
            if response_code != 200 or response is None:
                logger.error(f"获取图片失败, 状态码{response_code}")
                return []

        data = response.json()
        pics = data.get("data", [])
        if self._api == self._apis[0]:
            return pics

        for pic in pics:
            pic["source_url"] = f"https://www.pixiv.net/artworks/{pic['pid']}"
            pic["artist"] = {"name": pic["author"]}
            pic["pictures"] = [pic["urls"]]

        return pics

    async def _send_pics(self, pics: list[dict[str, Any]]):
        if not self.session:
            return
        if len(pics) < self._num:
            await self.send_msg(f"未找到指定数量的图片，仅找到 {len(pics)} 张")
        image_dir = (
            config.cache
            / self.session.group_id
            / self.session.user_id
            / str(self._pid)
            / "images"
        )
        image_dir.mkdir(parents=True, exist_ok=True)
        for pic in pics:
            title = pic["title"]
            source = pic["source_url"]
            artist = pic["artist"]["name"]
            img_urls = [img_url[self._size] for img_url in pic["pictures"]]
            text = f"标题: {title}\n作者: {artist}\n来源: {source}\n"
            msg = Message()
            msg.append(MessageSegment("text", {"text": text}))
            for img_url in img_urls:
                seg = MessageSegment("image", {"url": img_url})
                seg.data["summary"] = "我的新自拍喵[图片]"
                msg.append(seg)
            try:
                msg = await get_downloaded_msg(
                    image_dir, await dump_message(self.bot, (msg)), timeout=30
                )
                await self.send_msg(msg)
                logger.info("发送图片成功")
            except Exception as e:
                logger.error(f"发送图片失败: {e}")
                text += f"\n图片发送失败, 大概率被河蟹了, 请尝试私聊使用该命令\n{e}"
                await self.send_msg(text)

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

        if not self._check_perm("randpic"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        self._argv = new_argv
        self._parser.parse_argv(self._argv)

        r = self._parser.opts_value["-r"][0]
        if (r == "on" or r == "only") and not self._check_perm("nsfw"):
            await self.send_msg("权限不足")
            self.unlock()
            return
        if r == "on":
            self._r18 = 2
        elif r == "only":
            self._r18 = 1

        a = self._parser.opts_value["-a"][0]
        self._api = self._apis[random.randint(0, len(self._apis) - 1)]
        if a in ["1", "m", "manyacg"]:
            self._api = self._apis[0]
        elif a in ["2", "l", "lolicon"]:
            self._api = self._apis[1]

        self._num = self._parser.opts_value["-n"][0]
        self._num = max(self._num, 1)
        self._num = min(self._num, 20)
        if not self._check_perm("multisetu"):
            self._num = 1

        self._size = self._parser.opts_value["-s"][0]
        if self._api == self._apis[0]:
            self._size = "regular"

        self._keyword = self._parser.opts_value["-k"][0]
        if (
            self._keyword.replace(" ", "")
            .replace(",", "")
            .replace("|", "")
            .replace("&", "")
            == ""
        ):
            self._keyword = ""

        pics = await self._get_pics()
        if len(pics) < self._num and a == "r":
            self._api = self._apis[0] if self._api == self._apis[1] else self._apis[1]
            pics += await self._get_pics()
            pics = pics[: self._num]
        await self._send_pics(pics)
        self.unlock()
        return
