"""
# msgutils
Some utils to handle `Message` and `MessageSegment` by convert them to `DumpedMsg` and `DumpedSeg`
## DumpedMsg and DumpedSeg
Both of them are alias as follow:
```python
DumpedMsg = list[dict[str, Any]]
DumpedSeg = dict[str, Any]
```python
with the following schema:
```python
_MSG_SCHEMA = [
    {
        "type": str,
        "data": dict,
    }
]
```python
Use `dump_message` to get `DumpedMsg` and `DumpedSeg` by converting `Message` to `DumpedMsg`

As some features of the bot, equivalently, `DumpedMsg` and `DumpedSeg` can be represented as follow:
```haskell
data DumpedMsg = [DumpedSeg]
data DumpedSeg = TypeText | TypeImage | TypeVideo | TypeFile | ... | TypeForward | TypeReply | TypeNode
data TypeText = Text str
...
data TypeForward = Forward ... DumpedMsg
data TypeReply = Reply ... DumpedMsg
data TypeNode = Node ... DumpedMsg
```haskell
So the utils handle them functionally
## Functions
- `dump_message`: convert `Message` to `DumpedMsg`
- `msg_foldl`, `msg_foldr`, `msg_map`, `msg_filter`: functional combinator of DumpedMsg
- `get_multimedias_url`: get the urls of multimedias
- `modify_msg_data`: modify the datas of `DumpedMsg`
"""

from typing import Any, Callable, TypeVar

from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger

from .aux import validate_schema
from .config import config

_MSG_SCHEMA = [
    {
        "type": str,
        "data": dict,
    }
]
DumpedMsg = list[dict[str, Any]]
DumpedSeg = dict[str, Any]

B = TypeVar("B")

DELETE = object()
ORIGIN = object()


class DataVariables:
    def __init__(self, var_list: list):
        if var_list == []:
            raise ValueError("var_list cannot be empty")
        self.vars = var_list
        self.index = 0

    def reset(self):
        self.index = 0


def _set_node(
    *, user_id: int, nickname: str | None = None, content: DumpedMsg
) -> DumpedSeg:
    """
    Build a node
    """
    if nickname is None:
        nickname = str(user_id)
    node = {
        "type": "node",
        "data": {"user_id": user_id, "nickname": nickname, "content": content},
    }
    return node


def _get_forward_nodes(
    forward_msgs: DumpedMsg, *, depth: int = config.max_message_depth
) -> DumpedMsg:
    """
    Get the node list of a forward-type message
    """
    nodes = []
    if not forward_msgs:
        return []
    for forward_msg in forward_msgs:
        if (
            not forward_msg.get("sender")
            or not forward_msg.get("message")
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
            content = _get_forward_nodes(
                seg["data"].get("content", []), depth=depth - 1
            )
            node = _set_node(user_id=user_id, nickname=nickname, content=content)
            nodes.append(node)
            continue
        for seg in forward_msg.get("message", []):
            if seg["type"] != "forward":
                term = {"type": seg["type"], "data": seg["data"]}
                content.append(term)
                continue
            if depth <= 0:
                continue
            inner_content = _get_forward_nodes(
                seg["data"].get("content", []), depth=depth - 1
            )
            inner_node = _set_node(
                user_id=user_id, nickname=nickname, content=inner_content
            )
            content.append(inner_node)
        node = _set_node(user_id=user_id, nickname=nickname, content=content)
        nodes.append(node)

    return nodes


async def dump_message(bot: Bot, msg: Message) -> DumpedMsg:
    """
    Convert Message to DumpedMsg
        - bot: the bot instance
        - msg: the message
        - There will be `content` field for forward/reply/node-type segs, which is a DumpedMsg
            - Node has its own content, the function needs do nothing
            - Call `await bot.get_forward_msg` and `_get_forward_nodes` to get the content for a forward-type seg
            - Call `await bot.get_msg` to get the content for a reply-type seg
            - All DumpedSegs in the content of a forward-type seg are node-type
            - Node-type segs are used to represent a message in a forward/node-type seg
    """
    res = []
    for seg in msg:
        if seg.type == "forward":
            msg_id = seg.data.get("id")
            if msg_id is None:
                continue
            forward_data = await bot.get_forward_msg(id=msg_id)
            forward_msgs: DumpedMsg = forward_data.get("messages", [])
            content: DumpedMsg = _get_forward_nodes(forward_msgs)
            seg.data["content"] = content
        elif seg.type == "reply":
            reply_id = seg.data.get("id")
            if reply_id is None:
                continue
            reply_data = {}
            reply_data = await bot.get_msg(message_id=reply_id)
            content: DumpedMsg = reply_data.get("message", [])
            seg.data["content"] = content
        res.append({"type": seg.type, "data": seg.data})
    return res


def undump_message(dumped_msg: DumpedMsg) -> Message:
    """
    Convert DumpedMsg to Message
        - dumped_msg: the dumped message
    """
    if not validate_schema(dumped_msg, _MSG_SCHEMA):
        return Message()
    return Message(
        MessageSegment(dumped_seg["type"], dumped_seg["data"])
        for dumped_seg in dumped_msg
    )


async def send_msg(
    *,
    bot: Bot,
    group_id: int | None = None,
    user_id: int | None = None,
    msg: str | Message = "",
):
    """
    Send a message
        - bot: the bot instance
        - group_id: the group id
        - user_id: the user id
        - msg: the message
    """
    if group_id is None and user_id is None:
        logger.error("发送消息失败: group_id 和 user_id 不能同时为 None")
        return None
    if group_id is not None and user_id is not None:
        logger.error("发送消息失败: group_id 和 user_id 不能同时不为 None")
        return None
    if msg == Message():
        return None

    message_type = "group" if group_id is not None else "private"

    try:
        if isinstance(msg, Message) and len(msg) == 1 and msg[0].type == "forward":
            nodes = msg[0].data.get("content", [])
            if len(nodes) == 0:
                return None
            return await bot.send_forward_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                messages=nodes,
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


def _msg_walk_children(seg: DumpedSeg) -> DumpedMsg | None:
    """
    Get the content of a nestable seg
    """
    if seg["type"] in ("forward", "node", "reply"):
        return seg["data"].get("content")
    return None


def _seg_copy(seg: DumpedSeg) -> DumpedSeg:
    """
    Copy `seg` with 2 levels
    """
    return {"type": seg["type"], "data": dict(seg["data"])}


def msg_foldl(
    func: Callable[[B, DumpedSeg], B],
    initial: B,
    msg: DumpedMsg,
    *,
    depth: int = config.max_message_depth,
) -> B:
    """
    A functional combinator of DumpedMsg to fold it to a single value from left to right
    ```haskell
        msg_foldl :: (B -> DumpedSeg -> B) -> B -> DumpedMsg -> Int -> B
    ```haskell
        - `func(acc, seg)`: `acc` is the accumulated value, `seg` is the current DumpedSeg
            - **ATTENTION**: `func` shoudl not have any side effect to `msg`
        - `initial`: the initial value
        - `depth`: the max depth of recursion
    """
    if not validate_schema(msg, _MSG_SCHEMA) or depth < 0:
        return initial
    for seg in msg:
        initial = func(initial, seg)
        children = _msg_walk_children(seg)
        if children is not None:
            initial = msg_foldl(func, initial, children, depth=depth - 1)
    return initial


def msg_foldr(
    func: Callable[[DumpedSeg, B], B],
    initial: B,
    msg: DumpedMsg,
    *,
    depth: int = config.max_message_depth,
) -> B:
    """
    A functional combinator of DumpedMsg to fold it to a single value from right to left
    ```haskell
        msg_foldr :: (DumpedSeg -> B -> B) -> B -> DumpedMsg -> Int -> B
    ```haskell
        - `func(seg, acc)`: `seg` is the current `DumpedSeg`, `acc` is the accumulated value
            - **ATTENTION**: `func` shoudl not have any side effect to `msg`
        - `initial`: the initial value
        - `depth`: the max depth of recursion
    """
    if not validate_schema(msg, _MSG_SCHEMA) or depth < 0:
        return initial
    for seg in reversed(msg):
        children = _msg_walk_children(seg)
        if children is not None:
            initial = msg_foldr(func, initial, children, depth=depth - 1)
        initial = func(seg, initial)
    return initial


def msg_map(
    func: Callable[[DumpedSeg], DumpedSeg],
    msg: DumpedMsg,
    *,
    depth: int = config.max_message_depth,
) -> DumpedMsg:
    """
    A functional combinator of DumpedMsg to map it to get a new DumpedMsg
    ```haskell
        msg_map :: (DumpedSeg -> DumpedSeg) -> DumpedMsg -> Int -> DumpedMsg
    ```haskell
        - `func(seg)`: `seg` is a 2-level copy of the current `DumpedSeg`, `func(seg)` is the new `DumpedSeg` will be added
            - **ATTENTION**: `func` shoudl not have any side effect to `msg`
        - `depth`: the max depth of recursion
    """
    if not validate_schema(msg, _MSG_SCHEMA) or depth < 0:
        return msg
    result: DumpedMsg = []
    for seg in msg:
        new_seg = _seg_copy(seg)
        new_seg = func(new_seg)
        children = _msg_walk_children(new_seg)
        if children is not None:
            new_seg["data"]["content"] = msg_map(func, children, depth=depth - 1)
        result.append(new_seg)
    return result


def msg_filter(
    func: Callable[[DumpedSeg], bool],
    msg: DumpedMsg,
    *,
    depth: int = config.max_message_depth,
) -> DumpedMsg:
    """
    A functional combinator of DumpedMsg to filter it to get a new DumpedMsg
    ```haskell
        msg_filter :: (DumpedSeg -> Bool) -> DumpedMsg -> Int -> DumpedMsg
    ```haskell
        - `func(seg)`: `seg` is a 2-level copy of the current `DumpedSeg`, `func(seg)` is the bool will be used to judge if `seg` will be added
            - **ATTENTION**: `func` shoudl not have any side effect to `msg`
        - `depth`: the max depth of recursion
    """
    if not validate_schema(msg, _MSG_SCHEMA) or depth < 0:
        return msg
    result: DumpedMsg = []
    for seg in msg:
        if not func(seg):
            continue
        new_seg = _seg_copy(seg)
        children = _msg_walk_children(seg)
        if children is not None:
            new_seg["data"]["content"] = msg_filter(func, children, depth=depth - 1)
        result.append(new_seg)
    return result


def get_multimedias_url(
    msg: DumpedMsg,
    *,
    basetypes: list[str] = ["image", "video", "file"],
    depth: int = config.max_message_depth,
) -> list[str]:
    """
    Get the urls of multimedias from DumpedMsg
        - `msg`: the dumped message
        - `depth`: the max depth of recursion
        - `basetypes`: the types of multimedias
    """

    def _f(acc: list[str], seg: DumpedSeg) -> list[str]:
        if seg["type"] in basetypes:
            url = seg["data"].get("url", "")
            acc.append(url)
        return acc

    return msg_foldl(_f, [], msg, depth=depth)


def modify_msg_data(
    msg: DumpedMsg,
    data: dict[str, Any],
    basetypes: list[str],
    *,
    replace: bool = False,
    cover: bool = True,
    depth: int = config.max_message_depth,
) -> DumpedMsg:
    """
    Recursively modify the data of DumpedMsg
        - `msg`: the dumped message
        - `data`: the data used to modify
            - Set `data={..., key: value,...}` to assign all `key` with `value` in `msg`
            - Set `data={...,key: ORIGIN,...}` to assign all `key` with the original value of corresponding `key` in `msg` if it exists
            - Set `data={...,key: DELETE,...}` to delete all `key` in `msg`
            - Set `data={...,key: DataVariables(<non-empty list>),...}` will assign the i-th `key` in `msg` with the i-th element of the list
                - if i is out of range, it will assign `key` with the last element
                - call `<DataVariables Object>.reset()` to reset it if you want to use it in the function again
        - `basetypes`: the types of the data that will be modified
        - `depth`: the max depth of recursion
        - `replace`: set if the data should be replaced
        - `cover`: set if the data should be covered if `replace` is False
    """

    def _map(seg: DumpedSeg) -> DumpedSeg:
        if seg["type"] not in basetypes:
            return seg
        real_data = data.copy()
        for key, value in data.items():
            if value is ORIGIN:
                real_data[key] = seg["data"].get(key, ORIGIN)
                if real_data[key] is ORIGIN:
                    real_data.pop(key, None)
                continue
            if value is DELETE:
                real_data.pop(key, None)
                seg["data"].pop(key, None)
                continue
            if not isinstance(value, DataVariables):
                continue
            real_data[key] = (
                value.vars[value.index]
                if value.index < len(value.vars)
                else value.vars[-1]
            )
            value.index += 1
        if replace:
            seg["data"] = real_data
            return seg
        if cover:
            seg["data"].update(real_data)
            return seg
        for key, value in real_data.items():
            if key not in seg["data"]:
                seg["data"][key] = value
        return seg

    return msg_map(_map, msg, depth=depth)
