from __future__ import annotations

from typing import TYPE_CHECKING

from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment

from ..command import BotCommand
from ..config import config

if TYPE_CHECKING:
    from ..session import BotSession


# Simple auto reply, just for fun :). May be further reconstructed in future.
class BotCommandAutoReplyMain(BotCommand):
    _name = "autoreply_main"

    def __init__(self, bot: Bot, session: BotSession, *, _pid: int, _internal=None):
        super().__init__(bot, session, _pid=_pid, _internal=_internal)

    async def roger(self, event: MessageEvent):
        group_id = str(getattr(event, "group_id", "private"))
        if event.message_type == "private":
            group_id = "private"
        user_id = str(event.user_id)

        for seg in event.get_message():
            if seg.type != "text":
                continue
            text = seg.data.get("text", "")
            cleaned_text = (
                text.replace("!", "")
                .replace(" ", "")
                .replace("！", "")
                .replace("w", "")
                .replace("我", "")
            )
            if cleaned_text in [
                "csn",
                "草死你",
                "操死你",
                "🌿死你",
                "艹死你",
                "zjsncsn",
            ]:
                wcsn_path = config.client_base / "data" / "wcsn.jpg"
                msg = Message(MessageSegment.image(f"file://{wcsn_path}"))
                msg[0].data["sub_type"] = 1
                msg[0].data["summary"] = "喵呜~"
                await self.send_msg(msg, group_id=group_id, user_id=user_id)
                return
            cleaned = text.replace("?", "").replace(" ", "").replace("？", "")
            if cleaned in ["这是你吗", "zsnm", "是你吗"]:
                zsnm_path = config.client_base / "data" / "zsnm.jpg"
                msg = Message(
                    [
                        MessageSegment.image(f"file://{zsnm_path}"),
                        MessageSegment.text("是我。"),
                    ]
                )
                msg[0].data["sub_type"] = 1
                msg[0].data["summary"] = "喵呜~"
                await self.send_msg(msg, group_id=group_id, user_id=user_id)
                return

    async def run(self, args: Message):
        return
