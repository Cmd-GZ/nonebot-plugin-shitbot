from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Callable

autoreply_lock = asyncio.Lock()


class EndOfQueue:
    pass


async def prod_cons(
    inputs: asyncio.Queue,
    outputs: asyncio.Queue,
    func: Callable[..., Coroutine],
    *args,
    **kwargs,
):
    while True:
        item = await inputs.get()
        if isinstance(item, EndOfQueue):
            await outputs.put(EndOfQueue())
            break
        result = await func(item, *args, **kwargs)
        await outputs.put(result)
