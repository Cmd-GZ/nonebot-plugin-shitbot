import shutil
from pathlib import Path
from typing import Any

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
