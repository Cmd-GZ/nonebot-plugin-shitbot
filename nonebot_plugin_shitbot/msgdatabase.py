import uuid
from pathlib import Path

import httpx
import yaml
from nonebot.adapters.onebot.v11 import Message

from .aux import get_file_sha256, stuff_download, validate_schema
from .config import config
from .msgutils import (
    DELETE,
    MSG_SCHEMA,
    DataVariables,
    DumpedMsg,
    DumpedSeg,
    modify_msg_data,
    msg_foldl,
    msg_map,
    undump_message,
)


class BotMsgDataBase:
    def __init__(self, db_dir: Path):
        self._dir = db_dir
        self._medias_dir = self._dir / "medias"
        self._medias_rc_path = self._dir / "media_rc.yaml"
        self._msgs_dir = self._dir / "msgs"
        self._msgs_rc_path = self._dir / "msg_rc.yaml"
        self._cache_dir = config.cache / "database" / f"{uuid.uuid4().hex}"

        self._dir.mkdir(parents=True, exist_ok=True)
        self._medias_dir.mkdir(parents=True, exist_ok=True)
        self._medias_rc_path.touch(exist_ok=True)
        self._msgs_dir.mkdir(parents=True, exist_ok=True)
        self._msgs_rc_path.touch(exist_ok=True)

        self._medias_rc: dict[str, int] = {}
        self._msgs_rc: dict[str, int] = {}

        self._load_rc()

    @property
    def cache_dir(self):
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        return self._cache_dir

    @staticmethod
    def _get_multimedias_stuff(msg: DumpedMsg) -> list[tuple[str, str]]:
        def _f(acc: list[tuple[str, str]], seg: DumpedSeg) -> list[tuple[str, str]]:
            if seg["type"] not in ["image", "video", "file", "record"]:
                return acc
            url = seg["data"].get("url", "")
            file = seg["data"].get("file", "")
            if url:
                acc.append(("url", url))
            elif file:
                acc.append(("file", file))
            return acc

        return msg_foldl(_f, [], msg)

    def _load_rc(self):
        if not self._medias_rc_path.exists() or not self._msgs_rc_path.exists():
            return
        res = []
        for path in (self._medias_rc_path, self._msgs_rc_path):
            if not path.is_file():
                raise FileExistsError(f"Error: {path} is not a file")
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data is not None and not isinstance(data, dict):
                    raise ValueError
                if data is None:
                    data = {}
                res.append(data)
        self._medias_rc, self._msgs_rc = res

    def _update_rc(self):
        with self._medias_rc_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(self._medias_rc, f)
        with self._msgs_rc_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(self._msgs_rc, f)

    def _inc_media_rc(self, sha256: str):
        self._medias_rc[sha256] = self._medias_rc.get(sha256, 0) + 1

    def _dec_media_rc(self, sha256: str):
        rc = self._medias_rc.get(sha256)
        if rc is None:
            return
        self._medias_rc[sha256] = rc - 1

    def _save_media(self, media_path: Path):
        name = get_file_sha256(media_path)
        new_path = self._medias_dir / name
        if new_path.exists():
            return new_path
        media_path.rename(new_path)
        return new_path

    def _del_media(self, sha256: str):
        media_path = self._medias_dir / sha256
        if not media_path.exists():
            return
        rc = self._medias_rc.get(sha256)
        if rc is None or rc > 0:
            return
        media_path.unlink()
        del self._medias_rc[sha256]

    def get_msg(self, sha256: str) -> DumpedMsg:
        msg_path = self._msgs_dir / sha256
        if not msg_path.exists():
            return []
        return yaml.safe_load(msg_path.read_text(encoding="utf-8"))

    def inc_msg_rc(self, sha256: str):
        self._msgs_rc[sha256] = self._msgs_rc.get(sha256, 0) + 1
        self._update_rc()

    def dec_msg_rc(self, sha256: str):
        rc = self._msgs_rc.get(sha256)
        if rc is None:
            return
        self._msgs_rc[sha256] = rc - 1
        self._update_rc()

    async def _normalize_msg(
        self, msg: DumpedMsg, *, save_media: bool = False
    ) -> tuple[list[str], str, DumpedMsg]:
        if not validate_schema(msg, MSG_SCHEMA):
            raise ValueError("Invalid message")

        def _normalize_seg(seg: DumpedSeg) -> DumpedSeg:
            seg_type = seg["type"]
            seg_data = seg["data"]

            if seg_type == "text":
                text = seg["data"].get("text")
                seg_data = {}
                if text is not None:
                    seg_data["text"] = text

            if seg_type == "face":
                face_id = seg["data"].get("face_id")
                seg_data = {}
                if face_id is not None:
                    seg_data["face_id"] = face_id

            if seg_type == "image":
                url = seg["data"].get("url")
                file = seg["data"].get("file")
                sub_type = seg["data"].get("sub_type")
                summary = seg["data"].get("summary")
                seg_data = {}
                if url is not None:
                    seg_data["url"] = url
                if url is None and file is not None:
                    seg_data["file"] = file
                if sub_type is not None:
                    seg_data["sub_type"] = sub_type
                if summary is not None:
                    seg_data["summary"] = summary

            if seg_type in ["video", "file", "record"]:
                url = seg["data"].get("url")
                file = seg["data"].get("file")
                seg_data = {}
                if url is not None:
                    seg_data["url"] = url
                if url is None and file is not None:
                    seg_data["file"] = file

            if seg_type == "at":
                qq = seg["data"].get("qq")
                seg_data = {}
                if qq is not None:
                    seg_data["qq"] = qq

            if seg_type in ["rps", "dice"]:
                seg_data = {}

            if seg_type in ["contact", "music"]:
                _type = seg["data"].get("type")
                _id = seg["data"].get("id")
                seg_data = {}
                if _type is not None:
                    seg_data["type"] = _type
                if _id is not None:
                    seg_data["id"] = _id

            if seg_type in ["reply", "forward"]:
                content = seg["data"].get("content")
                seg_data = {}
                if content is not None:
                    seg_data["content"] = content

            if seg_type == "node":
                user_id = seg["data"].get("user_id")
                nickname = seg["data"].get("nickname")
                content = seg["data"].get("content")
                seg_data = {}
                if user_id is not None:
                    seg_data["user_id"] = user_id
                if nickname is not None:
                    seg_data["nickname"] = nickname
                if content is not None:
                    seg_data["content"] = content

            if seg_type == "json":
                json_data = seg["data"].get("data")
                seg_data = {}
                if json_data is not None:
                    seg_data["data"] = json_data

            seg["data"] = seg_data
            return seg

        msg = msg_map(_normalize_seg, msg)
        medias = []
        stuffs = self._get_multimedias_stuff(msg)
        download_dir = self._cache_dir / "download"
        download_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient() as client:
            for tpe, term in stuffs:
                if not term:
                    continue
                if tpe == "file":
                    medias.append(term)
                    continue
                temp_path = download_dir / uuid.uuid4().hex
                await stuff_download(client, term, temp_path)
                name = get_file_sha256(temp_path)
                medias.append(name)
                if save_media:
                    self._save_media(temp_path)
                temp_path.unlink(missing_ok=True)

        storable = modify_msg_data(
            msg,
            {"url": DELETE, "file": DataVariables(medias)},
            ["image", "video", "file", "record"],
        )
        msg = modify_msg_data(
            storable, {"summary": DELETE, "sub_type": DELETE}, ["image"]
        )
        msg = modify_msg_data(msg, {"user_id": DELETE, "nickname": DELETE}, ["node"])

        msg_temp_dir = self._cache_dir / "msg"
        msg_temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = msg_temp_dir / uuid.uuid4().hex
        temp_path.write_text(yaml.safe_dump(msg), encoding="utf-8")
        name = get_file_sha256(temp_path)
        temp_path.unlink()
        return medias, name, storable

    async def has_msg(self, msg: DumpedMsg) -> str | None:
        _, name, _ = await self._normalize_msg(msg, save_media=False)
        if self.get_msg(name):
            return name
        return None

    async def save_msg(self, msg: DumpedMsg, *, cover: bool = True) -> Path:
        medias, name, storable = await self._normalize_msg(msg, save_media=True)
        old_medias_raw: list[tuple[str, str]] = []

        msg_path = self._msgs_dir / name
        if msg_path.exists():
            if not cover:
                return msg_path
            old_msg = yaml.safe_load(msg_path.read_text(encoding="utf-8"))
            old_medias_raw = self._get_multimedias_stuff(old_msg)
            for _, media in old_medias_raw:
                if media != "":
                    self._dec_media_rc(media)

        for media in medias:
            self._inc_media_rc(media)
        for _, media in old_medias_raw:
            if media != "":
                self._del_media(media)
        
        self._update_rc()

        msg_path.write_text(yaml.safe_dump(storable), encoding="utf-8")
        return msg_path

    def del_msg(self, sha256: str):
        msg_path = self._msgs_dir / sha256
        if not msg_path.exists():
            return
        rc = self._msgs_rc.get(sha256)
        if rc is None or rc > 0:
            return

        msg = yaml.safe_load(msg_path.read_text(encoding="utf-8"))

        medias_raw = self._get_multimedias_stuff(msg)
        for _, media in medias_raw:
            if media == "":
                continue
            self._dec_media_rc(media)
            self._del_media(media)
        msg_path.unlink()
        del self._msgs_rc[sha256]
        self._update_rc()

    def prepare_send_msg(self, sha256: str) -> Message:
        msg = self.get_msg(sha256)
        contain_medias_dir = config.client_base / self._medias_dir.relative_to(
            config.bot_base
        )

        def _map(seg: DumpedSeg) -> DumpedSeg:
            if seg["type"] == "image":
                seg["data"]["file"] = (
                    f"file://{contain_medias_dir / seg['data']['file']!s}"
                )
            return seg

        msg = msg_map(_map, msg)
        return undump_message(msg)
