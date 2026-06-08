from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


class ShitBotConfig(BaseModel):
    bot_base: Path
    client_base: Path
    plugin_base: Path = Path()
    config: Path = Path()
    cache: Path = Path()
    data: Path = Path()
    permissions: Path = Path()
    script_png2v_path: Path = Path()
    script_p2png_path: Path = Path()
    script_png2fr_path: Path = Path()
    entries: dict[str, list]
    owners: list[str] | None
    max_message_depth: int
    pixiv_access_token: str

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="before")
    @classmethod
    def derive_paths(cls, data: Any) -> Any:
        if isinstance(data, dict):
            bot_base = data.get("bot_base")
            if bot_base is not None:
                bot_base = Path(bot_base)
                data["plugin_base"] = Path(__file__).parent
                data["config"] = bot_base / "config"
                data["cache"] = bot_base / "cache"
                data["data"] = bot_base / "data"
                data["script_p2png_path"] = data["plugin_base"] / "scripts" / "p2png.sh"
                data["script_png2v_path"] = data["plugin_base"] / "scripts" / "png2v.sh"
                data["script_png2fr_path"] = data["plugin_base"] / "scripts" / "png2fr.sh"
                data["permissions"] = data["config"] / "permissions"
        return data

    @classmethod
    def from_yaml(cls, file: Path) -> ShitBotConfig:
        if not file.exists():
            msg = f"The file doesn't exist: {file}"
            raise FileNotFoundError(msg)

        with file.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)


_config: dict[str, ShitBotConfig | None] = {"instance": None}


def get_config() -> ShitBotConfig:
    if _config["instance"] is None:
        config_path = Path(__file__).parent / "config.yaml"
        if not config_path.exists():
            default_config_path = Path(__file__).parent / "default_config.yaml"
            default_config_path.copy(config_path)
        _config["instance"] = ShitBotConfig.from_yaml(config_path)
    return _config["instance"]


config = get_config()
