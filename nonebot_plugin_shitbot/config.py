from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

# ── Permission entries (hard-coded, not read from file) ─────────────

_DEFAULT_ENTRIES: dict[str, list] = {
    "randpic": [
        "是否允许使用randpic命令",
        False,
        [],
        ["banned"],
        True,
        ["setu"],
        ["banned"],
    ],
    "advrandpic": [
        "是否允许使用advrandpic命令",
        False,
        [],
        ["banned"],
        True,
        ["setu"],
        ["banned"],
    ],
    "pixiv": [
        "是否允许使用pixiv命令",
        False,
        [],
        ["banned"],
        True,
        ["setu"],
        ["banned"],
    ],
    "nsfw": [
        "是否允许修改二次元图片相关命令的-r选项",
        True,
        ["nsfw"],
        ["banned"],
        True,
        ["nsfw"],
        ["banned"],
    ],
    "multisetu": [
        "是否允许一次获取多张二次元图片",
        False,
        [],
        ["banned"],
        True,
        ["multipic"],
        ["banned"],
    ],
    "convert": [
        "是否允许使用convert命令",
        True,
        ["convert"],
        ["banned"],
        True,
        ["convert"],
        ["banned"],
    ],
    "shitpost": [
        "是否允许使用shitpost命令",
        True,
        ["shitpost"],
        ["banned"],
        True,
        ["shitpost"],
        ["banned"],
    ],
    "help": ["是否允许使用help命令", False, [], ["banned"], False, [], ["banned"]],
    "md2pic": ["是否允许使用md2pic命令", False, [], ["banned"], False, [], ["banned"]],
    "session": [
        "是否允许使用session命令",
        False,
        [],
        ["banned"],
        False,
        [],
        ["banned"],
    ],
    "otherwise": [
        "是否会在错误命令输入后提示",
        False,
        [],
        ["banned"],
        False,
        [],
        ["banned"],
    ],
    "perm": [
        "是否允许使用perm命令的check选项",
        False,
        [],
        ["banned"],
        False,
        [],
        ["banned"],
    ],
    "permmanager": [
        "是否允许使用perm命令所有选项",
        True,
        [],
        ["banned"],
        True,
        [],
        ["banned"],
    ],
    "autoreplymanager": [
        "是否允许使用autoreply命令所有选项",
        True,
        [],
        ["banned"],
        True,
        [],
        ["banned"],
    ],
}


# ── Plugin configuration model (consumed by get_plugin_config) ──────
# Every field has a default → zero-config loadable.
# Users set overrides via scope-prefixed env vars, e.g.:
#   SHITBOT__CLIENT_CACHE=/app/cache/nonebot_plugin_shitbot
#   SHITBOT__CLIENT_DATA=/app/data/nonebot_plugin_shitbot
#   SHITBOT__OWNERS='["114514","1919810"]'
#   SHITBOT__MAX_MESSAGE_DEPTH=16
#   SHITBOT__PIXIV_ACCESS_TOKEN=kFccrAzYtHursDAyVmE50


class ShitBotConfig(BaseModel):
    """Scoped configuration fields — env vars use SHITBOT__ prefix."""

    client_cache: Path | None = None  # None = same filesystem as bot
    client_data: Path | None = None
    owners: list[str] | None = None
    max_message_depth: int = 16
    pixiv_access_token: str = ""


class PluginConfig(BaseModel):
    """Scope wrapper so that SHITBOT__CLIENT_CACHE, etc. are recognised."""

    shitbot: ShitBotConfig = ShitBotConfig()


# ── Runtime facade ──────────────────────────────────────────────────
# Wraps dotenv-sourced config with localstore-backed storage paths.
#   • Config.__init__ receives cache / data as *parameters* — it never
#     touches NoneBot or localstore itself.
#   • Unit tests (PYTEST_RUNNING) can pass dummy paths.
#   • Production caller (get_config) resolves localstore once.
#
# Config does NOT handle autoreply state — that is the responsibility
# of autoreply_cmd.py / handlers.py, which read/write data/autoreply/
# directly via config.data.


class Config:
    def __init__(self, user_config: ShitBotConfig, *, cache: Path, data: Path):
        self._uc = user_config
        self._cache = cache  # already resolved by caller
        self._data = data

    # -- user-config fields -------------------------------------------

    @property
    def client_cache(self) -> Path:
        """Container-side cache path; falls back to local cache if unset."""
        return self._uc.client_cache or self._cache

    @property
    def client_data(self) -> Path:
        """Container-side data path; falls back to local data if unset."""
        return self._uc.client_data or self._data

    @property
    def max_message_depth(self) -> int:
        return self._uc.max_message_depth

    @property
    def pixiv_access_token(self) -> str:
        return self._uc.pixiv_access_token

    # -- owners (dotenv only) -----------------------------------------

    @property
    def owners(self) -> list[str] | None:
        return self._uc.owners

    # -- entries (hard-coded) -----------------------------------------

    @property
    def entries(self) -> dict[str, list]:
        return _DEFAULT_ENTRIES

    # -- storage paths ------------------------------------------------

    @property
    def cache(self) -> Path:
        return self._cache

    @property
    def data(self) -> Path:
        return self._data


# ── Singleton (lazy — unit-test friendly) ───────────────────────────

_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        if os.environ.get("PYTEST_RUNNING"):
            # Unit test: no NoneBot driver, use bare defaults + dummy paths
            _config = Config(
                ShitBotConfig(),
                cache=Path("/tmp/shitbot_test_cache"),
                data=Path("/tmp/shitbot_test_data"),
            )
        else:
            # Production: one-shot localstore resolution
            from nonebot import get_plugin_config, require

            require("nonebot_plugin_localstore")
            import nonebot_plugin_localstore as store

            scoped = get_plugin_config(PluginConfig)
            _config = Config(
                scoped.shitbot,
                cache=store.get_plugin_cache_dir(),
                data=store.get_plugin_data_dir(),
            )
    return _config


def __getattr__(name: str):
    """Module-level lazy attribute for ``from .config import config``."""
    if name == "config":
        return get_config()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
