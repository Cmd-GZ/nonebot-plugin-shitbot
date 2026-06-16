from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .aux import validate_schema
from .config import config


class BotPermissions:
    _obj = None
    _sentinel = object()
    _perm_dir: Path
    _perm_users_path: Path
    _perm_owners_path: Path
    _perm_groups_path: Path
    _perm_entries_path: Path
    _users: dict[str, list[str]]
    _groups: dict[str, list[str]]
    _entries: dict[str, dict[str, Any]]

    _ENTRY_SCHEMA = {
        "description": str,
        "users": {
            "is_white": bool,
            "whites": [str],
            "blacks": [str],
        },
        "groups": {
            "is_white": bool,
            "whites": [str],
            "blacks": [str],
        },
    }

    _DEFAULT_ENTRY_SCHEMA = [str, bool, [str], [str], bool, [str], [str], None]

    # Use make() instead of this
    def __init__(self, *, _internal=None):
        if _internal is not self._sentinel:
            raise ValueError("请使用 BotPermissions.make() 方法创建实例")

        self._perm_dir = config.data / "permissions"
        if not self._perm_dir.exists():
            if self._perm_dir.is_file():
                raise FileExistsError(f"权限目录路径存在但不是目录: {self._perm_dir}")
            self._perm_dir.mkdir(parents=True)

        self._perm_users_path = self._perm_dir / "users.yaml"
        self._perm_owners_path = self._perm_dir / "owners.yaml"
        self._perm_groups_path = self._perm_dir / "groups.yaml"
        self._perm_entries_path = self._perm_dir / "entries.yaml"

        contents = []
        for path in (
            self._perm_users_path,
            self._perm_groups_path,
            self._perm_entries_path,
        ):
            if not path.exists():
                path.touch()
            if path.is_dir():
                raise FileExistsError(f"权限文件路径存在但不是文件: {path}")
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if data is not None and not isinstance(data, dict):
                    raise ValueError
                if data is None:
                    data = {}
                contents.append(data)
            except (yaml.YAMLError, ValueError):
                raise ValueError(f"权限文件 {path} 内容不是合法的 YAML 字典")

        self._users, self._groups, self._entries = contents
        if not all(
            validate_schema(entry, self._ENTRY_SCHEMA)
            for entry in self._entries.values()
        ):
            raise ValueError(f"权限文件 {self._perm_entries_path} 中的条目格式错误")

        if config.owners is None:
            self._perm_owners_path.unlink(missing_ok=True)
        owners = None
        if not self._perm_owners_path.exists() and config.owners is not None:
            self._perm_owners_path.write_text(
                yaml.safe_dump(config.owners), encoding="utf-8"
            )
        if self._perm_owners_path.exists():
            owners = yaml.safe_load(self._perm_owners_path.read_text(encoding="utf-8"))
        if owners is not None and not isinstance(owners, list):
            raise ValueError("owners获取失败")
        if owners is not None:
            self._users["owners"] = owners

        default_entries = config.entries
        default_entries_keys = default_entries.keys()
        entries_keys = self._entries.keys()
        deleted_keys = []
        is_inited = False
        for key in entries_keys:
            if key not in default_entries_keys:
                deleted_keys.append(key)
                is_inited = True
        for key in deleted_keys:
            del self._entries[key]
        try:
            for key in default_entries_keys:
                if len(default_entries[key]) < 7 or not validate_schema(
                    default_entries[key], self._DEFAULT_ENTRY_SCHEMA
                ):
                    raise ValueError(f"条目 {key} 格式错误")
                if key in self._entries:
                    continue
                self._entries[key] = {"users": {}, "groups": {}}
                self._init_entry(self._entries[key], default_entries[key])
                is_inited = True
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"权限项声明项entries格式错误: {e}")

        if not is_inited:
            return

        self.update_entries()

    @classmethod
    def make(cls) -> BotPermissions:
        if cls._obj is None:
            cls._obj = cls(_internal=cls._sentinel)
        return cls._obj

    @property
    def users(self) -> dict:
        return self._users

    @property
    def groups(self) -> dict:
        return self._groups

    @property
    def entries(self) -> dict:
        return self._entries

    @staticmethod
    def _init_entry(entry: dict[str, Any], default_entry: list[Any]):
        entry["description"] = default_entry[0]
        index = 1
        for perm_type in ("users", "groups"):
            for perm in ("is_white", "whites", "blacks"):
                entry[perm_type][perm] = default_entry[index]
                index += 1

    def update_users(self):
        users = self._users.copy()
        owners = users.pop("owners", None)
        self._perm_users_path.write_text(
            yaml.safe_dump(users, allow_unicode=True), encoding="utf-8"
        )
        self._perm_owners_path.write_text(
            yaml.safe_dump(owners, allow_unicode=True), encoding="utf-8"
        )

    def update_groups(self):
        self._perm_groups_path.write_text(
            yaml.safe_dump(self._groups, allow_unicode=True), encoding="utf-8"
        )

    def update_entries(self):
        self._perm_entries_path.write_text(
            yaml.safe_dump(self._entries, allow_unicode=True), encoding="utf-8"
        )

    def precheck_permission(self, entry_name: str, group_id: str, user_id: str) -> bool:
        entry = self._entries.get(entry_name)
        if entry is None:
            raise ValueError(f"权限条目不存在: {entry_name}")
        user_perm = entry["users"]
        group_perm = entry["groups"]

        if any(
            user_id in self._users.get(term, []) for term in user_perm["blacks"]
        ) or any(
            group_id in self._groups.get(term, []) for term in group_perm["blacks"]
        ):
            return False

        return (
            not user_perm["is_white"]
            or any(user_id in self._users.get(term, []) for term in user_perm["whites"])
        ) and (
            not group_perm["is_white"]
            or any(
                group_id in self._groups.get(term, []) for term in group_perm["whites"]
            )
        )

    def check_permission(self, entry_name: str, group_id: str, user_id: str) -> bool:
        if user_id in self._users.get("admins", []):
            return True
        return self.precheck_permission(entry_name, group_id, user_id)

    def owners_check_permission(
        self, entry_name: str, group_id: str, user_id: str
    ) -> bool:
        if user_id in self._users.get("owners", []):
            return True
        return self.precheck_permission(entry_name, group_id, user_id)


permissions = BotPermissions.make()
