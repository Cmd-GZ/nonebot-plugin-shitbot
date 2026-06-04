from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger

from ..aux import rm_cache, stuff_download
from ..command import BotCommand
from ..config import config
from ..parser import BotArgParser
from ..tasks import EndOfQueue, prod_cons

if TYPE_CHECKING:
    from ..session import BotSession

bash = shutil.which("bash") or "/bin/bash"


class BotCommandConvert(BotCommand):
    _name = "convert"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)
        self._mode = "video"
        self._runlock = asyncio.Lock()
        self._if_accept_pic = False
        self._prod_lock = asyncio.Lock()
        self._convert_lock = asyncio.Lock()
        self._urls: asyncio.Queue[str | EndOfQueue] = asyncio.Queue()
        self._downloads: asyncio.Queue[str | EndOfQueue] = asyncio.Queue()
        self._pngs: asyncio.Queue[str | EndOfQueue] = asyncio.Queue()
        self._outputs: asyncio.Queue[str | EndOfQueue] = asyncio.Queue()

    @property
    def if_accept_pic(self):
        return self._if_accept_pic

    @property
    def outputs(self):
        return self._outputs

    @property
    def prod_lock(self):
        return self._prod_lock

    @property
    def urls(self):
        return self._urls

    def _init_parser(self):
        parser = BotArgParser()
        start = parser.add_subparser("start")
        stop = parser.add_subparser("stop")
        start.set_rule(max=0)
        start.add_opt("-m", required=True, choice=["video", "frame"], default=["video"])
        stop.set_rule(max=0)
        parser.set_rule(max=0, need_subcmd=True)
        return parser

    @staticmethod
    async def _url_to_download(
        download_url: str, client: httpx.AsyncClient, download_dir: Path
    ):
        try:
            filename = f"{uuid.uuid4().hex}"
            save_path = download_dir / filename
            await stuff_download(client, download_url, save_path)
            logger.info(f"下载图片成功: {save_path}")
            return str(save_path)
        except Exception as e:
            logger.error(f"下载图片失败 {download_url}: {e}")
            return ""

    @staticmethod
    async def _download_to_png(download_path: str, png_dir: Path):
        if download_path == "":
            return ""
        png_path = png_dir / f"{uuid.uuid4().hex}.png"
        logger.info(
            f"执行图片转png脚本: {config.script_p2png_path} {download_path} {png_path}"
        )
        proc = await asyncio.create_subprocess_exec(
            bash,
            str(config.script_p2png_path),
            str(download_path),
            str(png_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            logger.info(f"脚本 stdout:\n{stdout.decode()}")
        if stderr:
            logger.warning(f"脚本 stderr:\n{stderr.decode()}")
        if proc.returncode != 0:
            logger.error(f"转换失败: {stderr.decode()[:]}")
            return ""
        logger.info(f"转换图片成功: {png_path}")
        return str(png_path)

    @staticmethod
    async def _png_to_video(png_path: str, video_dir: Path):
        if png_path == "":
            return ""
        video_path = video_dir / f"{uuid.uuid4().hex}.mp4"
        logger.info(
            f"执行图片转视频脚本: {config.script_png2v_path} {png_path} {video_path}"
        )
        proc = await asyncio.create_subprocess_exec(
            bash,
            str(config.script_png2v_path),
            str(png_path),
            str(video_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            logger.info(f"脚本 stdout:\n{stdout.decode()}")
        if stderr:
            logger.warning(f"脚本 stderr:\n{stderr.decode()}")
        if proc.returncode != 0:
            logger.error(f"转换失败: {stderr.decode()[:]}")
            return ""
        logger.info(f"转换视频成功: {video_path}")
        return str(video_path)

    @staticmethod
    async def _png_to_frame(png_path: str, frame_dir: Path):
        if png_path == "":
            return ""
        frame_path = frame_dir / f"{uuid.uuid4().hex}.png"
        logger.info(
            f"执行图片加框脚本: {config.script_png2fr_path} {png_path} {frame_path}"
        )
        proc = await asyncio.create_subprocess_exec(
            bash,
            str(config.script_png2fr_path),
            str(png_path),
            str(frame_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            logger.info(f"脚本 stdout:\n{stdout.decode()}")
        if stderr:
            logger.warning(f"脚本 stderr:\n{stderr.decode()}")
        if proc.returncode != 0:
            logger.error(f"转换失败: {stderr.decode()[:]}")
            return ""
        logger.info(f"转换方形图片成功: {frame_path}")
        return str(frame_path)

    async def _send_outputs(self):
        if not self.session:
            return
        outputs = []
        while True:
            output = await self._outputs.get()
            if isinstance(output, EndOfQueue):
                break
            if output == "":
                continue
            outputs.append(output)

        logger.info(f"用户 {self.session.user_id} 结束收集，共收到 {len(outputs)} 张")

        if len(outputs) == 0:
            await self.send_msg("没有输出被生成。")
            return

        await self.send_msg(f"共生成 {len(outputs)} 个输出，逐个发送…")

        for i, output in enumerate(outputs):
            output_file = Path(output)
            if not output_file.exists():
                logger.error(f"输出文件不存在: {output_file}")
                continue
            container_path = config.client_base / output_file.relative_to(
                config.bot_base
            )
            try:
                if self._mode == "video":
                    await self.send_msg(
                        Message(MessageSegment.video(f"file://{container_path}"))
                    )
                elif self._mode == "frame":
                    await self.send_msg(
                        Message(MessageSegment.image(f"file://{container_path}"))
                    )
                logger.info(f"发送第 {i + 1} 个输出成功: {output_file.name}")
            except Exception as e:
                logger.error(f"发送 {output_file.name} 失败: {e}")
                await self.send_msg(
                    f"发送 {output_file.name} 失败: {e}\n尝试以文件形式发送..."
                )
                try:
                    msg = Message(
                        MessageSegment("file", {"file": f"file://{container_path}"})
                    )
                    await self.send_msg(msg)
                    logger.info(
                        f"以文件形式发送第 {i + 1} 个输出成功: {output_file.name}"
                    )
                except Exception as e:
                    logger.error(f"发送 {output_file.name} 失败: {e}")
                    await self.send_msg(
                        f"发送第 {i + 1} 个输出 {output_file.name} 失败: {e}"
                    )

                await asyncio.sleep(0.25)

        await self.send_msg("输出发送完毕。")

    async def _convert_start(self):
        if not self.session:
            return
        downloads_dir = (
            config.cache
            / self.session.group_id
            / self.session.user_id
            / str(self._pid)
            / "downloads"
        )
        pngs_dir = (
            config.cache
            / self.session.group_id
            / self.session.user_id
            / str(self._pid)
            / "pngs"
        )
        outputs_dir = (
            config.cache
            / self.session.group_id
            / self.session.user_id
            / str(self._pid)
            / "outputs"
        )

        downloads_dir.mkdir(parents=True, exist_ok=True)
        pngs_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir.mkdir(parents=True, exist_ok=True)

        async def _urls_to_downloads():
            try:
                async with httpx.AsyncClient() as client:
                    await prod_cons(
                        self._urls,
                        self._downloads,
                        self._url_to_download,
                        client,
                        downloads_dir,
                    )
            except Exception as e:
                logger.exception(f"urls_to_downloads 管道异常退出: {e}")

        async def _downloads_to_pngs():
            try:
                await prod_cons(
                    self._downloads, self._pngs, self._download_to_png, pngs_dir
                )
            except Exception as e:
                logger.exception(f"downloads_to_pngs 管道异常退出: {e}")

        async def _pngs_to_outputs():
            try:
                async with self._convert_lock:
                    if self._mode == "video":
                        await prod_cons(
                            self._pngs, self._outputs, self._png_to_video, outputs_dir
                        )
                    elif self._mode == "frame":
                        await prod_cons(
                            self._pngs, self._outputs, self._png_to_frame, outputs_dir
                        )
            except Exception as e:
                logger.exception(f"pngs_to_outputs 管道异常退出: {e}")

        asyncio.create_task(_urls_to_downloads())
        asyncio.create_task(_downloads_to_pngs())
        asyncio.create_task(_pngs_to_outputs())

        logger.info(f"用户 {self.session.user_id} 开始了图片收集")
        await self.send_msg(
            "图片收集已开始， Bot 会收集本条信息后你发送的所有图片，直到你发送 /convert stop 完成收集。"
        )

        self._if_accept_pic = True
        return

    async def _convert_stop(self):
        if not self.session:
            return
        self._if_accept_pic = False

        await self.send_msg("转换图片中...")
        async with self._prod_lock:
            await self._urls.put(EndOfQueue())

        async with self._convert_lock:
            pass
        await self.send_msg("转换完毕。")

        await self._send_outputs()
        await rm_cache(self.session.group_id, self.session.user_id, str(self._pid))
        self.unlock()
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
                await self.send_msg(tip)
                return

            if self._argv is None and subcmd == "stop":
                tip = "错误：会话未开始\n"
                tip += "你还没有开始收集图片，请先使用 /convert start 。"
                await self.send_msg(tip)
                self.unlock()
                return

            self._argv = new_argv

            if self._pid >= 0 and not self._check_perm("convert"):
                await self.send_msg("权限不足")
                self.unlock()
                return

            if subcmd == "start":
                new_mode = self._parser.subparsers[subcmd].opts_value.get(
                    "-m", ["video"]
                )[0]  # type: ignore[index]
                self._mode = new_mode
                await self._convert_start()
                return

            if subcmd == "stop":
                await self._convert_stop()
                return
