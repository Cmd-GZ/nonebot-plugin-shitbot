
import asyncio
import io
import shutil
import httpx
import uuid
from PIL import Image
from pathlib import Path
from typing import Any

from nonebot.log import logger
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message

from nonebot_plugin_htmlrender import md_to_pic
from .config import getConfig
config = getConfig()

async def md_to_pic_auto_size(
    md_text: str,
    *,
    css_path: str = "",
    min_w: int = 20,
    max_w: int = 2000,
    min_h: int = 20,
    max_h: int | None = None,
    side_padding: int = 30,
    device_scale_factor=4,
) -> bytes:

    raw = await md_to_pic(md_text, width=max_w, css_path=css_path, device_scale_factor=device_scale_factor)
    img = Image.open(io.BytesIO(raw))
    min_w = int(device_scale_factor * min_w)
    min_h = int(device_scale_factor * min_h)
    max_h = int(device_scale_factor * max_h) if max_h is not None else max_h
    side_padding = int(device_scale_factor * side_padding)

    # Get the background color (the upper-left color)
    bgpx: Any = img.getpixel((0, 0))
    bgr, bgg, bgb = int(bgpx[0]), int(bgpx[1]), int(bgpx[2])

    def is_bg(r: int, g: int, b: int) -> bool:
        return abs(r - bgr) < 6 and abs(g - bgg) < 6 and abs(b - bgb) < 6

    def is_colunm_has_content(x: int):
        for y in range(0, h, 4):
            pixel: Any = img.getpixel((x, y))
            r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
            if not is_bg(r, g, b): return True
        return False

    def is_row_has_content(y: int):
        for x in range(0, w, 4):
            pixel: Any = img.getpixel((x, y))
            r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
            if not is_bg(r, g, b): return True
        return False

    w, h = img.size
    content_left, content_right = 0, w
    content_top, content_bottom = 0, h

    # Find out the leftest column that has content
    for x in range(0, w):
        if is_colunm_has_content(x):
            content_left = x
            break

    # Find out the rightest column that has content
    for x in range(w - 1, content_left - 1, -1):
        if is_colunm_has_content(x):
            content_right = x
            break

    # Find out the topest row that has content
    for y in range(0, h):
        if is_row_has_content(y):
            content_top = y
            break

    # Find out the bottomest row that has content
    for y in range(h - 1, content_top - 1, -1):
        if is_row_has_content(y):
            content_bottom = y
            break

    crop_left = max(0, content_left - side_padding)
    crop_right = max(crop_left + min_w, content_right + side_padding)
    crop_top = max(0, content_top - side_padding)
    crop_bottom = max(crop_top + min_h, content_bottom + side_padding)
    if max_h is not None:
        crop_bottom = min(crop_bottom, crop_top + max_h)

    crop_right = min(crop_right, w)
    crop_bottom = min(crop_bottom, h)
    img = img.crop((crop_left, crop_top, crop_right, crop_bottom))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

async def rmPath(path: Path):
    if not path.exists(): return
    if path.is_dir(): shutil.rmtree(path)
    if path.is_file(): path.unlink()


async def convertCleanup(group_id: str, user_id: str, pid: str):
    images_dir = config.bot_base / group_id / user_id / pid / "images"
    videos_dir = config.bot_base / group_id / user_id / pid / "videos"
    tar_path = config.bot_base / group_id / user_id / pid / f"{user_id}.tar"
    temp_dir = config.bot_base / group_id / user_id / pid / "temp"

    for path in [images_dir, videos_dir, tar_path, temp_dir]:
            await rmPath(path)
            logger.info(f"已删除: {path}")


async def sendMsg(bot: Bot, group_id: str, user_id: str, msg: str | Message):
    if group_id == "private":
        try:
            return await bot.send_private_msg(user_id=int(user_id), message=msg)
        except Exception as e:
            logger.error(f"发送 {msg} 失败: {e}")
            raise
    try:
        return await bot.send_group_msg(group_id=int(group_id), message=msg)
    except Exception as e:
        logger.error(f"发送 {msg} 失败: {e}")
        raise


async def stuffDownload(client: httpx.AsyncClient, url: str | httpx.URL, output_path: Path, *, referer: str | None = None):
    try:
        headers = {"Referer": referer} if referer is not None else {}
        async with client.stream("GET", url, headers=headers, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
    except Exception as e:
        logger.error(f"下载 {url} 失败: {e}")
        raise


def setNode(*, user_id: int, nickname: str | None = None, content: list[dict[str, Any]]) -> dict[str, Any]:
    if nickname is None: nickname = str(user_id)
    node = {
        "type": "node",
        "data": {
            "user_id": user_id,
            "nickname": nickname,
            "content": content
        }
    }
    return node


def getForwardNodes(forward_msgs: list[dict[str, Any]], depth: int, *, summary: str = "") -> list[dict[str, Any]]:
    nodes = []
    if not forward_msgs: return []
    for forward_msg in forward_msgs:
        if not forward_msg.get("sender"): continue
        if not forward_msg.get("message"): continue
        if not forward_msg["message"][0].get("type"): continue
        user_id = forward_msg["sender"].get("user_id", 0)
        nickname = forward_msg["sender"].get("nickname", None)
        content = []
        if len(forward_msg.get("message", [])) == 1 and forward_msg.get("message", [])[0]["type"] == "forward":
            if depth <= 0: continue
            seg = forward_msg.get("message", [])[0]
            content = getForwardNodes(seg["data"].get('content', []), depth - 1)
            node = setNode(user_id=user_id, nickname=nickname, content=content)
            if summary: node["data"]["summary"] = summary
            nodes.append(node)
            continue
        for seg in forward_msg.get("message", []):
            if seg["type"] != "forward":
                if summary: seg["data"]["summary"] = summary
                term = {"type": seg["type"], "data": seg["data"]}
                content.append(term)
                continue
            if depth <= 0: continue
            inner_content = getForwardNodes(seg["data"].get('content', []), depth - 1)
            inner_node = setNode(user_id=user_id, nickname=nickname, content=inner_content)
            if summary: inner_node["data"]["summary"] = summary
            content.append(inner_node)
        node = setNode(user_id=user_id, nickname=nickname, content=content)
        if summary: node["data"]["summary"] = summary
        nodes.append(node)

    return nodes

async def sendNodes(bot: Bot, group_id: str, user_id: str, nodes: list[dict[str, Any]]):
    if group_id == "private":
        try:
            return await bot.call_api('send_private_forward_msg', user_id=int(user_id), messages=nodes)
        except Exception as e:
            logger.error(f"发送合并信息失败: {e}")
            raise
    try:
        return await bot.call_api('send_group_forward_msg', group_id=int(group_id), messages=nodes)
    except Exception as e:
        logger.error(f"发送合并信息失败: {e}")
        raise


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