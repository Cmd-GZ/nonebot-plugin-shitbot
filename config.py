from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel
from typing import Dict, List, Optional

class ShitBotConfig(BaseModel):
    bot_base: Path
    client_base: Path
    script_png2v_path: Path
    script_p2png_path: Path
    temp_dir: Path
    whitelist_groups_setu: List[str]
    whitelist_users_setu: List[str]

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_yaml(cls, file: Path) -> ShitBotConfig:
        if not file.exists(): raise FileNotFoundError(f"The file doesn't exist: {file}")

        with open(file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)

_config_instance: Optional[ShitBotConfig] = None
def getConfig() -> ShitBotConfig:
    global _config_instance
    if _config_instance is None:
        config_path = Path(__file__).parent / "config.yaml"
        _config_instance = ShitBotConfig.from_yaml(config_path)
    return _config_instance