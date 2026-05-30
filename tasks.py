from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import (
    Message,
    MessageSegment,
)
from nonebot.log import logger

from .auxs import rm_path
from .config import config

if TYPE_CHECKING:
    from .commands.convert_cmd import BotCommandConvert

bash = shutil.which("bash") or "/bin/bash"


async def convert_p_to_png(command: BotCommandConvert):
    if not command.session:
        return
    bot = command.bot
    temp_images = command.temp_images
    images = command.images
    user_id = int(command.session.user_id)
    output_dir = (
        config.cache / "private" / command.session.user_id / str(command.pid) / "images"
    )
    await rm_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if_the_last = 0

    async with command.copy_lock:
        while True:
            index = len(images)
            if not command.if_accept_pic:
                async with command.download_lock:
                    pass
                if_the_last = 1

            while True:
                try:
                    temp_image = temp_images.get_nowait()
                except asyncio.QueueEmpty:
                    break
                image = output_dir / (f"{index:05d}.png")
                index += 1
                logger.info(
                    f"执行图片转png脚本: {config.script_p2png_path} {temp_image} {image}"
                )
                proc = await asyncio.create_subprocess_exec(
                    bash,
                    str(config.script_p2png_path),
                    str(temp_image),
                    str(image),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if stdout:
                    logger.info(f"脚本 stdout:\n{stdout.decode()}")
                if stderr:
                    logger.warning(f"脚本 stderr:\n{stderr.decode()}")
                if proc.returncode != 0:
                    await bot.send_private_msg(
                        user_id=user_id, message=f"转换失败: {stderr.decode()[:]}"
                    )
                    continue
                images.append(str(image))
            if if_the_last:
                return
            await command.p2png_event.wait()
            command.p2png_event.clear()


async def convert_png_to_v(command: BotCommandConvert):
    images = command.images
    videos = command.videos
    for image in images:
        if not Path(image).exists():
            logger.warning(f"图片文件不存在，跳过: {image}")
            continue
        video = str(Path(image).with_suffix(".mp4"))

        logger.info(f"执行转换脚本: {config.script_png2v_path} {image} {video}")
        proc = await asyncio.create_subprocess_exec(
            bash,
            str(config.script_png2v_path),
            str(image),
            str(video),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            logger.info(f"脚本 stdout:\n{stdout.decode()}")
        if stderr:
            logger.warning(f"脚本 stderr:\n{stderr.decode()}")

        if proc.returncode != 0:
            await command.send_msg(f"转换失败: {stderr.decode()[:]}")
            continue

        if not Path(video).exists():
            await command.send_msg(f"未生成视频文件: {video}")
            continue

        videos.append(video)
        logger.info(f"转换成功: {video}")


async def convert_send_videos(command: BotCommandConvert):

    await command.send_msg(f"共生成 {len(command.videos)} 个视频，逐个发送…")

    for video in command.videos:
        video_file = Path(video)
        if not video_file.exists():
            continue
        container_path = config.client_base / video_file.relative_to(config.bot_base)
        try:
            await command.send_msg(
                Message(MessageSegment.video(f"file://{container_path}")),
            )
            logger.info(f"发送视频成功: {video_file.name}")
        except Exception as e:
            logger.error(f"发送 {video_file.name} 失败: {e}")
            await command.send_msg(
                f"发送 {video_file.name} 失败: {e}\n尝试以文件形式发送..."
            )
            try:
                msg = Message(
                    MessageSegment("file", {"file": f"file://{container_path}"})
                )
                await command.send_msg(msg)
                logger.info(f"发送文件成功: {video_file.name}")
            except Exception as e:
                logger.error(f"发送 {video_file.name} 失败: {e}")
                await command.send_msg(f"发送 {video_file.name} 失败: {e}")

            await asyncio.sleep(0.25)

    await command.send_msg("视频发送完毕。")
