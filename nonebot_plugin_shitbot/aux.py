import hashlib
import re
import shutil
from pathlib import Path
from typing import Any, get_args, get_origin

import httpx
from nonebot.adapters.onebot.v11 import Bot
from nonebot.log import logger


def validate_schema(data: Any, schema: Any) -> bool:
    if schema is Any:
        return True
    if schema is None:
        return False

    origin = get_origin(schema)
    if origin is dict:
        key_type, value_type = get_args(schema)
        return isinstance(data, dict) and all(
            validate_schema(key, key_type) and validate_schema(value, value_type)
            for key, value in data.items()
        )
    if origin is list:
        (item_type,) = get_args(schema)
        return isinstance(data, list) and all(
            validate_schema(item, item_type) for item in data
        )

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


def rm_path(path: Path):
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    if path.is_file():
        path.unlink()


def get_file_sha256(file_path: Path | str):
    file = Path(file_path) if isinstance(file_path, str) else file_path
    if not file.is_file():
        raise FileNotFoundError(f"No such file or not a regular file: {file}")
    # Compute sha256sum
    with file.open("rb") as f:
        hash_hex = hashlib.file_digest(f, "sha256").hexdigest()
    return hash_hex


def rename_file_to_sha256(file_path: Path | str):
    file = Path(file_path) if isinstance(file_path, str) else file_path
    if not file.is_file():
        raise FileNotFoundError(f"No such file or not a regular file: {file}")
    # Compute sha256sum
    with file.open("rb") as f:
        hash_hex = hashlib.file_digest(f, "sha256").hexdigest()
    # Rename
    new_name = hash_hex
    new_path = file.with_name(new_name)
    file.rename(new_path)
    return new_path


async def stuff_download(
    client: httpx.AsyncClient,
    url: str | httpx.URL,
    output_path: Path,
    *,
    referer: str | None = None,
):
    try:
        if isinstance(url, str) and url.startswith("file://"):
            shutil.copyfile(url[7:], output_path)
            return
        headers = {"Referer": referer} if referer is not None else {}
        async with client.stream(
            "GET", url, headers=headers, follow_redirects=True
        ) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
    except Exception as e:
        logger.error(f"下载失败: {type(e).__name__}: {e!r}")
        raise


def is_sha256(name: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", name))


async def partition_botin_groups(
    bot: Bot, groups: list[int]
) -> tuple[list[int], list[int]]:
    bot_in_groups = set(group["group_id"] for group in await bot.get_group_list())
    bot_in_res = set(groups).intersection(bot_in_groups)
    bot_not_in_res = set(groups).difference(bot_in_groups)
    return list(bot_in_res), list(bot_not_in_res)
