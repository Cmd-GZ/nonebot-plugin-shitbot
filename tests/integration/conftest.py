"""Integration tests conftest: initializes the full NoneBot stack.

Only tests that need the real NoneBot driver/adapters/matchers live here.
Pure logic unit tests should go under tests/unit/ instead.
"""

import os

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import Adapter as V11Adapter
from nonebug import NONEBOT_START_LIFESPAN
from pytest_asyncio import is_async_test


def pytest_configure(config: pytest.Config):
    config.stash[NONEBOT_START_LIFESPAN] = False


def pytest_collection_modifyitems(items: list[pytest.Item]):
    pytest_asyncio_tests = [item for item in items if is_async_test(item)]
    session_scope_marker = pytest.mark.asyncio(loop_scope="session")
    for async_test in pytest_asyncio_tests:
        async_test.add_marker(session_scope_marker, append=False)


@pytest.fixture(scope="session", autouse=True)
async def after_nonebot_init(after_nonebot_init: None):
    driver = nonebot.get_driver()
    driver.register_adapter(V11Adapter)

    # The root conftest sets PYTEST_RUNNING=1 so that unit tests can import
    # pure-logic modules without pulling in the NoneBot stack.  Integration
    # tests need the full plugin though — temporarily clear the flag so that
    # __init__.py will import handler/command modules during plugin loading.
    # Restore it afterwards so that any late imports by unit tests are safe.
    pytest_running = os.environ.pop("PYTEST_RUNNING", None)

    nonebot.load_from_toml("pyproject.toml")

    if pytest_running is not None:
        os.environ["PYTEST_RUNNING"] = pytest_running
