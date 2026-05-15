import asyncio
import tarfile
from pathlib import Path

from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message
from nonebot.log import logger

from .config import getConfig
config = getConfig()

async def convertP2V(bot: Bot, user_id: str, img_dir: Path, video_dir: Path):
    try:
        user_id_int = int(user_id)
    except ValueError:
        logger.error(f"无效的 user_id: {user_id}")
        return
    try:
        logger.info(f"执行转换脚本: {config.script_p2v_path} {img_dir} {video_dir}")
        proc = await asyncio.create_subprocess_exec(
            str(config.script_p2v_path), str(img_dir), str(video_dir),
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