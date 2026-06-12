import hashlib
import shutil
from pathlib import Path
from typing import Any

import httpx
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
