from __future__ import annotations

from typing import TYPE_CHECKING

import time
import random
import asyncio
import json

from pathlib import Path
from yt_dlp import YoutubeDL

from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger

from ..command import BotCommand
from ..config import config
from ..parser import BotArgParser
from ..msgutils import undump_message

if TYPE_CHECKING:
    from ..session import BotSession
    from yt_dlp import _Params


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
        return parser

    async def _parse_videos(self, ydl: YoutubeDL, videos_dir: Path):
        def _parseor():
            for link in self._links:
                time.sleep(random.uniform(1, 3))
                try:
                    info = ydl.extract_info(link, download=False)
                    if info is None:
                        raise ValueError(f"链接无效或无法提取信息")
                except Exception as e:
                    logger.error(f"提取{link}信息失败: {e}")
                    self._infos.append((False, Message(MessageSegment.text(f"提取视频信息失败"))))
                    self._video_paths.append(None)
                    continue

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

                try:
                    res = ydl.process_ie_result(info, download=True)
                    downloads = (res or {}).get("requested_downloads") or []
                    video_path_str = downloads[0].get("filepath") if downloads else None
                    if not video_path_str or not Path(video_path_str).is_file():
                        raise ValueError(f"未产出有效文件")
                    self._video_paths.append(Path(video_path_str))
                except Exception as e:
                    logger.error(f"下载{link}失败: {e}")
                    self._video_paths.append(None)
                    continue

        await asyncio.to_thread(_parseor)

    async def run(self, args: Message):
        if not self.session:
            return
        pre_argv = []
        if len(args) >= 1 and args[0].type == "reply":
            reply_stuff = await self.bot.get_msg(message_id=args[0].data["id"])
            pre_argv = undump_message(reply_stuff["message"]).extract_plain_text().strip().split()
            for seg in reply_stuff["message"]:
                if seg["type"] != "json":
                    continue
                sub_json = json.loads(seg.get("data", {}).get("data") or "{}")
                link = sub_json.get("meta", {}).get("detail_1", {}).get("qqdocurl", "")
                if "b23.tv/" not in link and "bilibili.com/video/" not in link:
                    continue
                self._links.append(link)

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

        contexts = pre_argv + self._parser.value

        for seg in contexts:
            link = ""
            if "b23.tv/" in seg:
                link = f"https://b23.tv/{seg.split('b23.tv/')[-1]}"
            elif "bilibili.com/video/" in seg:
                link = f"https://www.bilibili.com/video/{seg.split('bilibili.com/video/')[-1]}"
            elif "BV" in seg:
                link = f"https://www.bilibili.com/video/BV{seg.split('BV')[-1]}"
            elif "av" in seg:
                link = f"https://www.bilibili.com/video/av{seg.split('av')[-1]}"
            if not link:
                continue
            self._links.append(link)

        if not self._links:
            await self.send_msg("未检测到有效链接")
            self.unlock()
            return

        videos_dir = (
            config.cache
            / self.session.group_id
            / self.session.user_id
            / str(self._pid)
            / "videos"
        )
        videos_dir.mkdir(parents=True, exist_ok=True)

        opts: _Params = {
            "no_warnings": True,
            "noplaylist": True,
            "format_sort": [f"res:{720}", "vcodec:h264"],
            "merge_output_format": "mp4",
            "outtmpl": str(videos_dir / "%(id)s.%(ext)s"),
        }
        with YoutubeDL(opts) as ydl:
            await self._parse_videos(ydl, videos_dir)

        for video_path, info in zip(self._video_paths, self._infos):
            try:
                await self.send_msg(info[1])
            except Exception as e:
                logger.error(f"发送消息失败: {e}")
                if info[1][-1].type != "image":
                    continue
                info[1][-1] = MessageSegment.text("\n封面获取失败")
                await self.send_msg(info[1])
            if not info[0]:
                continue
            if not video_path:
                await self.send_msg("视频下载失败")
                continue
            container_path = config.client_cache / video_path.relative_to(config.cache)
            try:
                await self.send_msg(
                    Message(MessageSegment.video(f"file://{container_path}"))
                )
            except Exception as e:
                logger.error(f"发送视频失败: {e}")
                await self.send_msg("视频发送失败")


        self.unlock()
