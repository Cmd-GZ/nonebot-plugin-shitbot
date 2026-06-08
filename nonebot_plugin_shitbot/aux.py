import shutil
from pathlib import Path
from typing import Any, Callable, TypeVar

import httpx
from nonebot.adapters.onebot.v11 import Bot, Message
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
        if (
            not forward_msg.get("sender")
            or not forward_msg["sender"].get("message")
            or not forward_msg["message"][0].get("type")
        ):
            continue
        user_id = forward_msg["sender"].get("user_id", 0)
        nickname = forward_msg["sender"].get("nickname", None)
        content = []
        if (
            len(forward_msg.get("message", [])) == 1
            and forward_msg.get("message", [{}])[0].get("type") == "forward"
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


async def dump_message(bot: Bot, msg: Message) -> list[dict[str, Any]]:
    res = []
    for seg in msg:
        if seg.type == "forward":
            msg_id = seg.data.get("id")
            if msg_id is None:
                continue
            forward_data = await bot.get_forward_msg(id=msg_id)
            forward_msgs = forward_data.get("messages", [])
            content = get_forward_nodes(forward_msgs, config.max_message_depth)
            seg.data["content"] = content
        elif seg.type == "reply":
            reply_id = seg.data.get("id")
            if reply_id is None:
                continue
            reply_data = {}
            reply_data = await bot.get_msg(message_id=reply_id)
            content = reply_data.get("message", [])
            seg.data["content"] = content
        res.append({"type": seg.type, "data": seg.data})
    return res


_MSG_SCHEMA = [
    {
        "type": str,
        "data": dict,
    }
]

B = TypeVar("B")


def _msg_walk_children(seg: dict[str, Any]) -> list[dict[str, Any]] | None:
    if seg["type"] in ("forward", "node", "reply"):
        return seg["data"].get("content")
    return None


def _seg_copy(seg: dict[str, Any]) -> dict[str, Any]:
    return {"type": seg["type"], "data": dict(seg["data"])}


def msg_foldl(
    func: Callable[[B, dict[str, Any]], B],
    initial: B,
    msg: list[dict[str, Any]],
    depth: int,
) -> B:
    if not validate_schema(msg, _MSG_SCHEMA) or depth < 0:
        return initial
    for seg in msg:
        initial = func(initial, seg)
        children = _msg_walk_children(seg)
        if children is not None:
            initial = msg_foldl(func, initial, children, depth - 1)
    return initial


def msg_foldr(
    func: Callable[[dict[str, Any], B], B],
    initial: B,
    msg: list[dict[str, Any]],
    depth: int,
) -> B:
    if not validate_schema(msg, _MSG_SCHEMA) or depth < 0:
        return initial
    for seg in reversed(msg):
        children = _msg_walk_children(seg)
        if children is not None:
            initial = msg_foldr(func, initial, children, depth - 1)
        initial = func(seg, initial)
    return initial


def msg_map(
    func: Callable[[dict[str, Any]], dict[str, Any]],
    msg: list[dict[str, Any]],
    depth: int,
) -> list[dict[str, Any]]:
    if not validate_schema(msg, _MSG_SCHEMA) or depth < 0:
        return msg
    result: list[dict[str, Any]] = []
    for seg in msg:
        new_seg = _seg_copy(seg)
        new_seg = func(new_seg)
        children = _msg_walk_children(new_seg)
        if children is not None:
            new_seg["data"]["content"] = msg_map(func, children, depth - 1)
        result.append(new_seg)
    return result


def msg_filter(
    func: Callable[[dict[str, Any]], bool], msg: list[dict[str, Any]], depth: int
) -> list[dict[str, Any]]:
    if not validate_schema(msg, _MSG_SCHEMA) or depth < 0:
        return msg
    result: list[dict[str, Any]] = []
    for seg in msg:
        if not func(seg):
            continue
        new_seg = _seg_copy(seg)
        children = _msg_walk_children(seg)
        if children is not None:
            new_seg["data"]["content"] = msg_filter(func, children, depth - 1)
        result.append(new_seg)
    return result


def get_multimedias_url(
    msg: list[dict[str, Any]],
    depth: int,
    *,
    basetypes: list[str] = ["image", "video", "file"],
) -> list[str]:
    def _f(acc: list[str], seg: dict[str, Any]) -> list[str]:
        if seg["type"] in basetypes:
            url = seg["data"].get("url", "")
            acc.append(url)
        return acc

    return msg_foldl(_f, [], msg, depth)


class DataVarable:
    def __init__(self, var_list: list | None):
        self.vars = var_list


def modify_msg_data(
    msg: list[dict[str, Any]],
    data: dict[str, Any],
    basetypes: list[str],
    depth: int,
    *,
    replace: bool = False,
    cover: bool = True,
) -> list[dict[str, Any]]:
    def _map(seg: dict[str, Any]) -> dict[str, Any]:
        if seg["type"] not in basetypes:
            return seg
        real_seg = {"type": seg["type"], "data": dict(seg["data"])}
        real_data = data.copy()
        for key, value in data.items():
            if not isinstance(value, DataVarable):
                continue
            if value.vars is None:
                real_data.pop(key, None)
                real_seg["data"].pop(key, None)
                continue
            if value.vars == []:
                return real_seg
            real_data[key] = value.vars[0]
            if len(value.vars) > 1:
                value.vars.pop(0)
        if replace:
            real_seg["data"] = real_data
            return real_seg
        if cover:
            real_seg["data"].update(real_data)
            return real_seg
        for key, value in real_data.items():
            if key not in real_seg["data"]:
                real_seg["data"][key] = value
        return real_seg

    return msg_map(_map, msg, depth)
