import asyncio
import shutil
import httpx
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from nonebot.log import logger
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message

from .config import getConfig
config = getConfig()

async def rmPath(path: Path):
    if not path.exists(): return
    if path.is_dir(): shutil.rmtree(path)
    if path.is_file(): path.unlink()


async def convertCleanup(group_id: str, user_id: str):
    images_dir = config.bot_base / group_id / user_id / "images"
    videos_dir = config.bot_base / group_id / user_id / "videos"
    tar_path = config.bot_base / group_id / user_id / f"{user_id}.tar"
    temp_dir = config.bot_base / group_id / user_id / "temp"

    for path in [images_dir, videos_dir, tar_path, temp_dir]:
            await rmPath(path)
            logger.info(f"已删除: {path}")


async def sendMsg(bot: Bot, group_id: str, user_id: str, msg: str | Message):
    if group_id == "private":
        try:
            await bot.send_private_msg(user_id=int(user_id), message=msg)
        except Exception as e:
            logger.error(f"发送 {msg} 失败: {e}")
        return
    try:
        await bot.send_group_msg(group_id=int(group_id), message=msg)
    except Exception as e:
        logger.error(f"发送 {msg} 失败: {e}")
    return


async def stuffDownload(client: httpx.AsyncClient, url: str | httpx.URL, output_path: Path):
    resp = await client.get(url, follow_redirects=True)
    resp. raise_for_status()
    output_path.write_bytes(resp.content)


async def getImagesUrl(bot: Bot, event_reply: Reply | None, event_msg: Message, depth: int):
    rax = []

    reply_segs = []
    if event_reply:
        reply_msgs = await bot.get_msg(message_id=event_reply.message_id)
        reply_segs = Message([MessageSegment(seg['type'], seg['data']) for seg in reply_msgs['message']])

    segs = reply_segs + event_msg

    for seg in segs:
        if seg.type not in ["image", "forward", "reply"]: continue
        if seg.type  != "image" and depth <= 0: continue

        # base case
        if seg.type == "image":
            url = seg.data.get('url', "")
            if not url: continue
            rax.append(url)
            continue

        msg_id = seg.data.get('id', "")
        if not msg_id: continue

        # rec case 1
        if seg.type == "reply":
            try:
                reply_msg = await bot.get_msg(message_id=msg_id)
                reply_segs = Message([MessageSegment(seg['type'], seg['data']) for seg in reply_msg['message']])
                rax += await getImagesUrl(bot, None, reply_segs, depth - 1)
            except Exception as e:
                logger.error(f"获取引用消息失败 (ID: {msg_id}): {e}")
            continue

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
                rax += await getImagesUrl(bot, None, message_segs, depth - 1)
            continue

    return rax