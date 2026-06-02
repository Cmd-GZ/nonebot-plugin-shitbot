import shutil
from pathlib import Path
from typing import Any

import httpx
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.log import logger

from .config import config


def validate_schema(data: Any, schema: Any) -> bool:
    if schema is Any:
        return True
    if schema is None:
        return False
    if isinstance(schema, type):
        return isinstance(data, schema)
    if isinstance(schema, dict):
        if not isinstance(data, dict):
            return False
        return all(
            key in data and validate_schema(data[key], subschema)
            for key, subschema in schema.items()
        )
    if isinstance(schema, list):
        if not isinstance(data, list):
            return False
        length = len(schema)
        if length < 1:
            return False
        return all(
            validate_schema(item, schema[i if i < length else -1])
            for i, item in enumerate(data)
        )
    return False


async def rm_path(path: Path):
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    if path.is_file():
        path.unlink()


async def rm_cache(group_id: str, user_id: str, pid: str):
    cache_path = config.cache / group_id / user_id / pid
    await rm_path(cache_path)
    logger.info(f"已删除缓存: {cache_path}")


async def send_msg(
    *,
    bot: Bot,
    group_id: int | None = None,
    user_id: int | None = None,
    msg: str | Message | list[dict[str, Any]] = "",
):
    if group_id is None and user_id is None:
        logger.error("发送消息失败: group_id 和 user_id 不能同时为 None")
        return None
    if group_id is not None and user_id is not None:
        logger.error("发送消息失败: group_id 和 user_id 不能同时不为 None")
        return None

    message_type = "group" if group_id is not None else "private"

    try:
        if isinstance(msg, list) and not isinstance(msg, Message):
            return await bot.send_forward_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                messages=msg,
            )

        return await bot.send_msg(
            message_type=message_type,
            user_id=user_id,
            group_id=group_id,
            message=msg,
        )
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        raise


async def stuff_download(
    client: httpx.AsyncClient,
    url: str | httpx.URL,
    output_path: Path,
    *,
    referer: str | None = None,
):
    try:
        headers = {"Referer": referer} if referer is not None else {}
        async with client.stream(
            "GET", url, headers=headers, follow_redirects=True
        ) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
    except Exception as e:
        logger.error(f"下载 {url} 失败: {e}")
        raise


def set_node(
    *, user_id: int, nickname: str | None = None, content: list[dict[str, Any]]
) -> dict[str, Any]:
    if nickname is None:
        nickname = str(user_id)
    node = {
        "type": "node",
        "data": {"user_id": user_id, "nickname": nickname, "content": content},
    }
    return node


def get_forward_nodes(
    forward_msgs: list[dict[str, Any]], depth: int, *, summary: str = ""
) -> list[dict[str, Any]]:
    nodes = []
    if not forward_msgs:
        return []
    for forward_msg in forward_msgs:
        if not forward_msg.get("sender"):
            continue
        if not forward_msg.get("message"):
            continue
        if not forward_msg["message"][0].get("type"):
            continue
        user_id = forward_msg["sender"].get("user_id", 0)
        nickname = forward_msg["sender"].get("nickname", None)
        content = []
        if (
            len(forward_msg.get("message", [])) == 1
            and forward_msg.get("message", [])[0]["type"] == "forward"
        ):
            if depth <= 0:
                continue
            seg = forward_msg.get("message", [])[0]
            content = get_forward_nodes(seg["data"].get("content", []), depth - 1)
            node = set_node(user_id=user_id, nickname=nickname, content=content)
            if summary:
                node["data"]["summary"] = summary
            nodes.append(node)
            continue
        for seg in forward_msg.get("message", []):
            if seg["type"] != "forward":
                if summary:
                    seg["data"]["summary"] = summary
                term = {"type": seg["type"], "data": seg["data"]}
                content.append(term)
                continue
            if depth <= 0:
                continue
            inner_content = get_forward_nodes(seg["data"].get("content", []), depth - 1)
            inner_node = set_node(
                user_id=user_id, nickname=nickname, content=inner_content
            )
            if summary:
                inner_node["data"]["summary"] = summary
            content.append(inner_node)
        node = set_node(user_id=user_id, nickname=nickname, content=content)
        if summary:
            node["data"]["summary"] = summary
        nodes.append(node)

    return nodes


async def get_images_url(
    bot: Bot, event_reply: Reply | None, event_msg: Message, depth: int
) -> list[str]:
    rax = []

    reply_segs = []
    if event_reply:
        reply_msgs = await bot.get_msg(message_id=event_reply.message_id)
        reply_segs = Message(
            [MessageSegment(seg["type"], seg["data"]) for seg in reply_msgs["message"]]
        )

    segs = reply_segs + event_msg

    for seg in segs:
        if seg.type not in ["image", "forward", "reply"]:
            continue
        if seg.type != "image" and depth <= 0:
            continue

        # base case
        if seg.type == "image":
            url = seg.data.get("url", "")
            if not url:
                continue
            rax.append(url)
            continue

        msg_id = seg.data.get("id", "")
        if not msg_id:
            continue

        # rec case 1
        if seg.type == "reply":
            try:
                reply_msg = await bot.get_msg(message_id=msg_id)
                reply_segs = Message(
                    [
                        MessageSegment(seg["type"], seg["data"])
                        for seg in reply_msg["message"]
                    ]
                )
                rax += await get_images_url(bot, None, reply_segs, depth - 1)
            except Exception as e:
                logger.error(f"获取引用消息失败 (ID: {msg_id}): {e}")
            continue

        if seg.type == "forward":
            forward_msgs = seg.data.get("content")
            if forward_msgs is None:
                try:
                    forward_data = await bot.call_api(
                        "get_forward_msg", message_id=msg_id
                    )
                    forward_msgs = forward_data.get("messages", [])
                except Exception as e:
                    logger.error(f"获取转发消息失败 (ID: {msg_id}): {e}")
                    continue
            if not forward_msgs:
                continue
            for forward_msg in forward_msgs:
                message_segs = Message(
                    [
                        MessageSegment(seg["type"], seg["data"])
                        for seg in forward_msg.get("message", [])
                    ]
                )
                rax += await get_images_url(bot, None, message_segs, depth - 1)
            continue

    return rax
