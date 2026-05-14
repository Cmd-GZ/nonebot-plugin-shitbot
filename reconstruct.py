import os
import re
import shutil
import asyncio
import tarfile
import uuid
import httpx
from pathlib import Path
from typing import Dict, List, Optional
from itertools import chain

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.log import logger



# ===CONFIG=== #

BOTBASE = Path("/home/user/qqbot/docker/QQ")
CLIENTBASE = Path("/app/.config/QQ")
SCRIPTPATH = Path("/home/user/qqbot/p2v.sh")
TEMPDIR = Path("/tmp/qqbot_temp")
BOTBASE.mkdir(parents=True, exist_ok=True)
TEMPDIR.mkdir(parents=True, exist_ok=True)



# ===Maintained=== #

users_status: Dict[str, str] = {}
users_convert_status: Dict[str, bool] = {}
users_convert_images: Dict[str, List[str]] = {}
users_convert_locks: Dict[str, asyncio.Lock] = {}



# ===Auxiliary functions=== #

async def rmPath(path: Path):
    if not path.exists(): return
    if path.is_dir(): shutil.rmtree(path)
    if path.is_file(): path.unlink()


async def convertCleanup(user_id: str):
    images_dir = BOTBASE / "images" / user_id
    videos_dir = BOTBASE / "videos" / user_id
    tar_path = BOTBASE / f"{user_id}.tar"
    temp_dir = TEMPDIR  / user_id

    for path in [images_dir, videos_dir, tar_path, temp_dir]:
            await rmPath(path)
            logger.info(f"已删除: {path}")
    users_convert_locks.pop(user_id, None)


async def imagesDownload(bot: Bot, event_reply: Optional[Reply], event_msg: Message, client: httpx.AsyncClient, dldir: Path, user_id: str, depth: int):
    reply_segs = []
    if event_reply:
        reply_msgs = await bot.get_msg(message_id=event_reply.message_id)
        reply_segs = Message([MessageSegment(seg['type'], seg['data']) for seg in reply_msgs['message']])
    segs = reply_segs + event_msg
    for seg in segs:
        if seg.type not in ["image", "forward", "reply"]: continue
        if seg.type != "image" and depth <= 0: continue

        # base case
        if seg.type == "image":
            img_url = seg.data.get('url', '')
            if not img_url: continue

            orig_file = seg.data.get('file', 'image')
            safe_name = f"{uuid.uuid4().hex}"
            save_path = dldir / safe_name

            try:
                resp = await client.get(img_url, follow_redirects=True)
                resp.raise_for_status()
                save_path.write_bytes(resp.content)
                users_convert_images[user_id].append(str(save_path))
                logger.info(f"下载图片成功: {save_path}")
            except Exception as e:
                logger.error(f"下载图片失败 {img_url}: {e}")

        msg_id = seg.data.get('id', '')
        if not msg_id: continue

        # rec case 1
        if seg.type == "reply":
            try:
                reply_msg = await bot.get_msg(message_id=msg_id)
                reply_segs = Message([MessageSegment(seg['type'], seg['data']) for seg in reply_msg['message']])
                await imagesDownload(bot, None, reply_segs, client, dldir, user_id, depth - 1)
            except Exception as e:
                logger.error(f"获取引用消息失败 (ID: {msg_id}): {e}")
                continue

        # rec cases 2
        if seg.type == "forward":
            forward_msgs = seg.data.get('content')
            if forward_msgs is None:
                try:
                    forward_data = await bot.call_api('get_forward_msg', message_id=msg_id)
                    forward_msgs = forward_data.get('messages', [])
                except Exception as e:
                    logger.error(f"获取转发消息失败 (ID: {msg_id}): {e}")
                    continue
            if not forward_msgs: continue

            for forward_msg in forward_msgs:
                message_segs = Message([MessageSegment(seg['type'], seg['data']) for seg in forward_msg.get('message', [])])
                await imagesDownload(bot, None, Message(message_segs), client, dldir, user_id, depth - 1)
            continue

# ===Commands managers=== #

cmd_convert = on_command("convert", priority=1, block=True)
@cmd_convert.handle()
async def handleCmdConvert(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if event.message_type != "private": return

    argv = args.extract_plain_text().strip().split()

    if not argv or len(argv) != 1 or (argv[0] != "start" and argv[0] != "stop"):
        tip =  "命令格式错误。\n"
        tip += "输入 /help convert 查看使用方法."
        await cmd_convert.finish(tip)

    user_id = str(event.user_id)
    status = users_status.get(user_id)

    if status != None and (status != "convert start" or argv[0] == "start"):
        tip =  "错误：会话被占用\n"
        tip += f"命令 {status} 正在运行，进行下一步前请先终止它或等待其完成。"
        await cmd_convert.finish(tip)

    if status == None and argv[0] == "stop":
        tip =  "错误：先前未执行 /convert start 。\n"
        tip += "你还没有开始收集图片，请先使用 /convert start 。"
        await cmd_convert.finish(tip)

    # Now we have just two cases: `status == None and argv[0] == "start"` and `status == "convert start" and argv[0] == "stop"`.
    # Both of them are legal

    if argv[0] == "start":
        users_status[user_id] = "convert start"
        logger.info(f"用户 {user_id} 开始了图片收集")

        users_convert_locks[user_id] = asyncio.Lock()
        users_convert_images[user_id] = []
        await cmd_convert.send("图片收集已开始， Bot 会收集本条信息后你发送的所有图片，直到你发送 /convert stop 完成收集。")
        users_convert_status[user_id] = True
        await cmd_convert.finish()

    if argv[0] == "stop":
        users_status[user_id] = "convert stop"
        users_convert_status[user_id] = False
        lock = users_convert_locks.get(user_id)
        if lock:
            await cmd_convert.send("下载图片中...")
            async with lock:
                pass
            await cmd_convert.send("下载完毕。")
        temp_images_path = users_convert_images.pop(user_id, [])
        if not temp_images_path:
            users_status.pop(user_id, "")
            await cmd_convert.finish("本次没有收集到任何图片。")

        logger.info(f"用户 {user_id} 结束收集，共收到 {len(temp_images_path)} 张")

        images_dir = BOTBASE / "images" / user_id
        videos_dir = BOTBASE / "videos" / user_id
        await rmPath(images_dir)
        await rmPath(videos_dir)
        images_dir.mkdir(parents=True, exist_ok=True)
        videos_dir.mkdir(parents=True, exist_ok=True)

        count = 0

        for i, temp_image_path in enumerate(temp_images_path):
            if not Path(temp_image_path).exists():
                logger.warning(f"图片 {temp_image_path} 不存在，跳过")
                continue

            new_name = f"{count:05d}"
            image_path = images_dir / new_name
            shutil.copy2(temp_image_path, image_path)
            logger.info(f"复制图片: {temp_image_path} -> {image_path}")
            count += 1

        if count == 0:
            await convertCleanup(user_id)
            users_status.pop(user_id, "")
            await cmd_convert.finish("没有有效的图片被保存。")

        await cmd_convert.send(f"有效保存 {count} 张图片，开始处理…")

        async def _runTask():
            try:
                await convertP2V(bot, user_id, images_dir, videos_dir)
            except Exception:
                pass
            finally:
                await convertCleanup(user_id)
                users_status.pop(user_id, "")

        asyncio.create_task(_runTask())

        await cmd_convert.finish()


cmd_help = on_command("help", priority=1, block=True)
@cmd_help.handle()
async def handleCmdHelp(event: MessageEvent, args: Message = CommandArg()):
    if event.message_type != "private": return

    argv = args.extract_plain_text().strip().split()

    tip =  "使用方法：\n"
    tip += "  /help          显示帮助\n"
    tip += "  /convert       收集图片并批量转换为视频\n"
    tip += "\n"
    tip += "使用例子：\n"
    tip += "  /help help"

    if not argv:
        await cmd_help.finish(tip)


    if argv[0] == "help":
        tip =  "/help:           显示帮助\n"
        tip += "命令格式：\n"
        tip += "  /help          显示基础帮助\n"
        tip += "  /help <命令>   显示<命令>的使用方法\n"
        tip += "\n"
        tip += "使用例子：\n"
        tip += "  /help convert  获取 /convert 命令的使用方法"

    if argv[0] == "convert":
        tip =  "/convert:        收集图片并批量转换为视频\n"
        tip += "命令格式：\n"
        tip += "  /convert start 令 Bot 保存在提示出现后你接下来发送的图片，直至你输入 /convert stop \n"
        tip += "  /convert stop  在输入 /convert start 并发送图片后输入， Bot 将停止保存你发送的图片，转而将收集到的图片按顺序转换为视频发送，最后打包发送一个 tar 归档。"

    await cmd_help.finish(tip)


cmd_otherwise = on_command("", priority=2, block=True)
@cmd_otherwise.handle()
async def handleCmdOtherwise(event: MessageEvent):
    if event.message_type != "private": return
    await cmd_otherwise.finish("无效命令，请输入/help获取帮助。")



# ===Massages managers=== #

msg_convert = on_message(priority=10, block=False)
@msg_convert.handle()
async def handleMsgConvert(bot: Bot, event: MessageEvent):
    if event.message_type != "private": return
    user_id = str(event.user_id)
    lock = users_convert_locks.get(user_id)
    if lock is None: return

    async with lock:
        if not users_convert_status.get(user_id): return

        temp_images_dir = TEMPDIR / user_id
        temp_images_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient() as client:
            await imagesDownload(bot, event.reply, event.get_message(), client, temp_images_dir, user_id, 5)


# ===asyncio Tasks=== #

async def convertP2V(bot: Bot, user_id: str, img_dir: Path, video_dir: Path):
    try:
        user_id_int = int(user_id)
    except ValueError:
        logger.error(f"无效的 user_id: {user_id}")
        return
    try:
        logger.info(f"执行转换脚本: {SCRIPTPATH} {img_dir} {video_dir}")
        proc = await asyncio.create_subprocess_exec(
            str(SCRIPTPATH), str(img_dir), str(video_dir),
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
                container_path = CLIENTBASE / video_file.relative_to(BOTBASE)
                await bot.send_private_msg(user_id=user_id_int, message=Message(MessageSegment.video(f"file://{container_path}")))
                logger.info(f"发送视频成功: {video_file.name}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"发送 {video_file.name} 失败: {e}")
                await bot.send_private_msg(user_id=user_id_int, message=f"发送 {video_file.name} 失败: {e}")

        tar_path = BOTBASE / f"{user_id}.tar"
        with tarfile.open(tar_path, "w") as tar:
            for video_file in videos:
                tar.add(video_file, arcname=video_file.name)

        container_tar = CLIENTBASE / tar_path.relative_to(BOTBASE)
        logger.info(f"打包完成: {tar_path}")
        await bot.upload_private_file(user_id=user_id_int, file=f"file://{container_tar}", name="videos.tar")
        await bot.send_private_msg(user_id=user_id_int, message="视频打包文件已发送。")

    except Exception as e:
        logger.error(f"处理异常: {e}")
        await bot.send_private_msg(user_id=user_id_int, message="处理过程出错")