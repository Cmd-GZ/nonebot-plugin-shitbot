from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

# User-configurable fields model.
# ShitBotConfig is declared in PluginMetadata.config so that NoneFlow
# can introspect the plugin's configuration schema.


class ShitBotConfig(BaseModel):
    bot_base: Path  # persistent storage root (cache / data / config live here)
    client_base: Path  # client-side persistent storage root (for container deploys)
    entries: dict[str, list]  # permission entries for each command
    owners: list[str] | None = None
    max_message_depth: int = 10
    if_auto_start_autoreply: bool = True
    pixiv_access_token: str = ""

    @classmethod
    def from_yaml(cls, file: Path) -> ShitBotConfig:
        if not file.exists():
            raise FileNotFoundError(f"config file not found: {file}")
        with file.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        model_fields = cls.model_fields.keys()
        filtered = {k: v for k, v in data.items() if k in model_fields}
        return cls(**filtered)


# Path proxy / facade.
# Keeps the existing config.cache / config.data / config.permissions
# interface while delegating actual storage to nonebot-plugin-localstore.
# - User-facing fields (max_message_depth, ...) proxy directly to ShitBotConfig
#   and are always available (no NoneBot dependency).
# - Storage paths (cache / data / config / permissions) lazily require localstore
#   on first access.


class Config:
    def __init__(self, user_config: ShitBotConfig):
        self._uc = user_config
        self._plugin_base = Path(__file__).parent
        self._store: Any = None  # lazily populated by _store_get()

    # --- user-config fields (no NoneBot dependency) ---

    @property
    def bot_base(self) -> Path:
        return self._uc.bot_base

    @property
    def client_base(self) -> Path:
        return self._uc.client_base

    @property
    def entries(self) -> dict[str, list]:
        return self._uc.entries

    @property
    def owners(self) -> list[str] | None:
        return self._uc.owners

    @property
    def max_message_depth(self) -> int:
        return self._uc.max_message_depth

    @property
    def if_auto_start_autoreply(self) -> bool:
        return self._uc.if_auto_start_autoreply

    @property
    def pixiv_access_token(self) -> str:
        return self._uc.pixiv_access_token

    # --- storage paths (lazily load localstore) ---

    @property
    def cache(self) -> Path:
        return self._store_get().get_plugin_cache_dir()

    @property
    def data(self) -> Path:
        return self._store_get().get_plugin_data_dir()

    @property
    def config(self) -> Path:
        """localstore config dir (not the user-written config.yaml)."""
        return self._store_get().get_plugin_config_dir()

    @property
    def permissions(self) -> Path:
        return self.config / "permissions"

    # --- read-only attributes ---

    @property
    def plugin_base(self) -> Path:
        return self._plugin_base

    def _store_get(self) -> Any:
        """Lazily initialise localstore.

        On the first access to a storage path we inject bot_base
        subdirectories into the environment so that localstore picks
        them up, then require-and-import the plugin.
        """
        if self._store is None:
            _inject_localstore_env(self._uc.bot_base)
            from nonebot import require

            require("nonebot_plugin_localstore")
            import nonebot_plugin_localstore as store

            self._store = store
        return self._store


# Singleton

_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        config_path = Path(__file__).parent / "config.yaml"
        if not config_path.exists():
            default_config_path = Path(__file__).parent / "default_config.yaml"
            with (
                open(default_config_path, encoding="utf-8") as src,
                open(config_path, "w", encoding="utf-8") as dst,
            ):
                dst.write(src.read())
        _config = Config(ShitBotConfig.from_yaml(config_path))
    return _config


def _inject_localstore_env(bot_base: Path) -> None:
    """Inject bot_base subdirs into localstore's plugin-level env vars.

    Defaults point at bot_base/{cache,data,config}.  If the user has
    already set any of these env vars (e.g. in dotenv) the existing
    values are preserved.
    """
    plugin_id = "nonebot_plugin_shitbot"
    for env_var, subdir in [
        ("LOCALSTORE_PLUGIN_CACHE_DIR", "cache"),
        ("LOCALSTORE_PLUGIN_DATA_DIR", "data"),
        ("LOCALSTORE_PLUGIN_CONFIG_DIR", "config"),
    ]:
        existing = os.environ.get(env_var)
        mapping: dict[str, str] = {}
        if existing:
            try:
                mapping = json.loads(existing)
                if not isinstance(mapping, dict):
                    mapping = {}
            except (json.JSONDecodeError, TypeError):
                pass
        mapping.setdefault(plugin_id, str(bot_base / subdir))
        os.environ[env_var] = json.dumps(mapping, separators=(",", ":"))


def __getattr__(name: str):
    """Module-level lazy attribute.

    `from .config import config` calls get_config() on first access so
    that the localstore require is not triggered during unit tests
    (PYTEST_RUNNING environment).
    """
    if name == "config":
        return get_config()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
