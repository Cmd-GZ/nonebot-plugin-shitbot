from __future__ import annotations

import asyncio
import io
import json
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger
from yt_dlp import YoutubeDL

from ..command import BotCommand
from ..config import config
from ..msgutils import undump_message
from ..parser import BotArgParser

if TYPE_CHECKING:
    from yt_dlp import _Params

    from ..session import BotSession


class BotCommandBilibili(BotCommand):
    _name = "bilibili"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._links = []
        self._infos = []
        self._video_paths = []

    def _init_parser(self):
        parser = BotArgParser()
        parser.set_rule(min=0)
        parser.add_opt("--res", required=True, type=int, default=[720])
        return parser

    @staticmethod
    def _cookie_stream(cookie: str) -> io.StringIO:
        lines = ["# Netscape HTTP Cookie File"]
        for item in cookie.split(";"):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            lines.append(
                f".bilibili.com\tTRUE\t/\tFALSE\t0\t{key.strip()}\t{value.strip()}"
            )
        return io.StringIO("\n".join(lines) + "\n")

    async def _preprocess_reply(self, args: Message):
        if not args or args[0].type != "reply":
            return []

        try:
            reply = await self.bot.get_msg(message_id=args[0].data["id"])
        except Exception as e:
            logger.error(f"获取回复消息失败: {e}")
            return []

        # Get link from json card
        for seg in reply["message"]:
            if seg["type"] != "json":
                continue
            try:
                sub_json = json.loads(seg.get("data", {}).get("data") or "{}")
            except (ValueError, TypeError, AttributeError):
                continue
            link = sub_json.get("meta", {}).get("detail_1", {}).get("qqdocurl", "")
            if "b23.tv/" not in link and "bilibili.com/video/" not in link:
                continue
            self._links.append(link)

        # Return preprocessed reply text message
        return undump_message(reply["message"]).extract_plain_text().strip().split()

    def _get_link(self, context: str):
        link = ""
        if "b23.tv/" in context:
            link = f"https://b23.tv/{context.rsplit('b23.tv/', maxsplit=1)[-1]}"
        elif "bilibili.com/video/" in context:
            link = f"https://www.bilibili.com/video/{context.rsplit('bilibili.com/video/', maxsplit=1)[-1]}"
        elif "BV" in context:
            link = f"https://www.bilibili.com/video/BV{context.rsplit('BV', maxsplit=1)[-1]}"
        elif "av" in context:
            link = f"https://www.bilibili.com/video/av{context.rsplit('av', maxsplit=1)[-1]}"
        return link

    def _parse_video(self, ydl: YoutubeDL, link: str):
        try:
            info = ydl.extract_info(link, download=False)
            if info is None:
                raise ValueError("链接无效或无法提取信息")
        except Exception as e:
            logger.error(f"提取{link}信息失败: {e}")
            self._infos.append(
                (False, Message(MessageSegment.text("提取视频信息失败")))
            )
            self._video_paths.append(None)
            return

        # Get video info
        identity = info.get("id") or ""
        title = info.get("title") or ""
        author = info.get("uploader") or ""
        cover = info.get("thumbnail") or ""
        if cover.startswith("http://"):
            cover = "https://" + cover[len("http://") :]
        text = f"标题: {title}\nUP主: {author}\nBV: {identity}"
        msg = Message()
        msg.append(MessageSegment.text(text))
        if cover:
            msg.append(MessageSegment.image(cover))
        self._infos.append((True, msg))

        # Download video
        try:
            res = ydl.process_ie_result(info, download=True)
            downloads = (res or {}).get("requested_downloads") or []
            video_path_str = downloads[0].get("filepath") if downloads else None
            if not video_path_str or not Path(video_path_str).is_file():
                raise ValueError("未产出有效文件")
            self._video_paths.append(Path(video_path_str))
        except Exception as e:
            logger.error(f"下载{link}失败: {e}")
            self._video_paths.append(None)
            return

    async def _parse_videos(self, ydl: YoutubeDL):
        def _parseor():
            for link in self._links:
                time.sleep(random.uniform(1, 3))
                self._parse_video(ydl, link)

        await asyncio.to_thread(_parseor)

    async def _send_video(self, video_path: Path | None, info: tuple[bool, Message]):
        try:
            await self.send_msg(info[1])
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            if info[1][-1].type != "image":
                return
            info[1][-1] = MessageSegment.text("\n封面获取失败")
            await self.send_msg(info[1])
        if not info[0]:
            return
        if not video_path:
            await self.send_msg("视频下载失败")
            return
        container_path = config.client_cache / video_path.relative_to(config.cache)
        try:
            await self.send_msg(
                Message(MessageSegment.video(f"file://{container_path}"))
            )
        except Exception as e:
            logger.error(f"发送视频失败: {e}")
            await self.send_msg("视频发送失败")

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

        if not self._check_perm("bilibili"):
            await self.send_msg("权限不足")
            self.unlock()
            return

        # Preprocess reply message
        reply_argv = await self._preprocess_reply(args)
        contexts = reply_argv + self._parser.value

        # Get video links
        for context in contexts:
            link = self._get_link(context)
            if link:
                self._links.append(link)

        if not self._links:
            await self.send_msg("未检测到有效链接")
            self.unlock()
            return

        # Download videos
        videos_dir = (
            config.cache
            / self.session.group_id
            / self.session.user_id
            / str(self._pid)
            / "videos"
        )
        res = self._parser.opts_value["--res"][0]
        videos_dir.mkdir(parents=True, exist_ok=True)
        opts: _Params = {
            "no_warnings": True,
            "noplaylist": True,
            "format_sort": [f"res:{res}", "vcodec:h264"],
            "merge_output_format": "mp4",
            "outtmpl": str(videos_dir / "%(id)s.%(ext)s"),
        }
        if config.bilibili_cookie:
            cookie = self._cookie_stream(config.bilibili_cookie)
            opts["cookiefile"] = cast("str", cookie)
            logger.info("已加载 bilibili cookie")
        with YoutubeDL(opts) as ydl:
            await self._parse_videos(ydl)

        # Send videos
        for video_path, info in zip(self._video_paths, self._infos):
            await self._send_video(video_path, info)

        self.unlock()
