from __future__ import annotations
from typing import TYPE_CHECKING

import asyncio
import tarfile
from pathlib import Path
from typing import Dict, List, Optional

from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message
from nonebot.log import logger

from .session import BotSession
from .auxiliaries import rmPath
from .config import getConfig
config = getConfig()

if TYPE_CHECKING:
    from .command import BotCommand, BotCommandConvert

async def convertPng2V(bot: Bot, user_id: str, img_dir: Path, video_dir: Path):
    try:
        user_id_int = int(user_id)
    except ValueError:
        logger.error(f"无效的 user_id: {user_id}")
        return
    try:
        logger.info(f"执行转换脚本: {config.script_png2v_path} {img_dir} {video_dir}")
        proc = await asyncio.create_subprocess_exec(
            str(config.script_png2v_path), str(img_dir), str(video_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            logger.info(f"脚本 stdout:\n{stdout.decode()}")
        if stderr:
            logger.warning(f"脚本 stderr:\n{stderr.decode()}")

        if proc.returncode != 0:
            await bot.send_private_msg(user_id=user_id_int, message=f"转换失败: {stderr.decode()[:]}")
            return
        if not video_dir.exists() or not any(video_dir.iterdir()):
            await bot.send_private_msg(user_id=user_id_int, message="未生成视频文件。")
            return

        videos = sorted([f for f in video_dir.iterdir() if f.is_file() and f.suffix == '.mp4'])
        if not videos:
            await bot.send_private_msg(user_id=user_id_int, message="未找到 mp4 视频文件。")
            return

        await bot.send_private_msg(user_id=user_id_int, message=f"共生成 {len(videos)} 个视频，逐个发送…")

        for i, video_file in enumerate(videos, 1):
            if not video_file.exists(): continue
            size_mb = video_file.stat().st_size / (1024 * 1024)
            if size_mb > 100:
                await bot.send_private_msg(user_id=user_id_int, message=f"视频 {video_file.name} 过大，跳过")
                continue
            try:
                container_path = config.client_base / video_file.relative_to(config.bot_base)
                await bot.send_private_msg(user_id=user_id_int, message=Message(MessageSegment.video(f"file://{container_path}")))
                logger.info(f"发送视频成功: {video_file.name}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"发送 {video_file.name} 失败: {e}")
                await bot.send_private_msg(user_id=user_id_int, message=f"发送 {video_file.name} 失败: {e}")

        tar_path = config.bot_base / f"{user_id}.tar"
        with tarfile.open(tar_path, "w") as tar:
            for video_file in videos:
                tar.add(video_file, arcname=video_file.name)

        container_tar = config.client_base / tar_path.relative_to(config.bot_base)
        logger.info(f"打包完成: {tar_path}")
        await bot.upload_private_file(user_id=user_id_int, file=f"file://{container_tar}", name="videos.tar")
        await bot.send_private_msg(user_id=user_id_int, message="视频打包文件已发送。")

    except Exception as e:
        logger.error(f"处理异常: {e}")
        await bot.send_private_msg(user_id=user_id_int, message="处理过程出错")


async def convertP2Png(command: BotCommandConvert):
    if not command.session: return
    bot = command.bot
    temp_images = command.temp_images
    images = command.images
    user_id = int(command.session.user_id)
    output_dir = config.bot_base/ "images" / command.session.user_id
    await rmPath(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if_the_last = 0

    async with command.copy_lock:
        while True:
            index = len(images)
            if command.if_accept_pic == False:
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
                logger.info(f"执行图片转png脚本: {config.script_p2png_path} {temp_image} {image}")
                proc = await asyncio.create_subprocess_exec(
                    "/bin/bash", str(config.script_p2png_path), str(temp_image), str(image),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if stdout:
                    logger.info(f"脚本 stdout:\n{stdout.decode()}")
                if stderr:
                    logger.warning(f"脚本 stderr:\n{stderr.decode()}")
                if proc.returncode != 0:
                    await bot.send_private_msg(user_id=user_id, message=f"转换失败: {stderr.decode()[:]}")
                    continue
                images.append(str(image))
            if if_the_last: return
            await command.p2png_event.wait()
            command.p2png_event.clear()

