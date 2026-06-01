from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class ShitBotConfig(BaseModel):
    bot_base: Path
    config: Path
    cache: Path
    data: Path
    client_base: Path
    script_png2v_path: Path
    script_p2png_path: Path
    script_png2fr_path: Path
    whitelist_groups_setu: list[str]
    whitelist_users_setu: list[str]
    max_message_depth: int
    pixiv_access_token: str

    model_config = ConfigDict(arbitrary_types_allowed=True)

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
        _config["instance"] = ShitBotConfig.from_yaml(config_path)
    return _config["instance"]


config = get_config()
