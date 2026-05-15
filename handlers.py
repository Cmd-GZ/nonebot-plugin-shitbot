import asyncio

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.log import logger

from .config import getConfig
from .session import BotSession
from .command import BotCommand, BotCommandHelp

config = getConfig()




# ===Commands handlers=== #
cmd_help = on_command("help", priority=1, block=True)
@cmd_help.handle()
async def handleCmdHelp(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if event.message_type != "private": return
    session = BotSession.make("private", str(event.user_id))
    command = BotCommandHelp.make(session, args)
    if not command:
        tip =  "错误：会话被占用\n"
        tip += f"命令 {session.command} 正在运行，进行下一步前请先终止它或等待其完成。"
        await cmd_otherwise.finish(tip)

    await command.run(bot)
    await cmd_otherwise.finish()

cmd_otherwise = on_command("", priority=2, block=True)
@cmd_otherwise.handle()
async def handleCmdOtherwise(bot: Bot, event: MessageEvent):
    if event.message_type != "private": return
    session = BotSession.make("private", str(event.user_id))
    command = BotCommand.make(session)
    if not command:
        tip =  "错误：会话被占用\n"
        tip += f"命令 {session.command} 正在运行，进行下一步前请先终止它或等待其完成。"
        await cmd_otherwise.finish(tip)

    await command.run(bot)
    await cmd_otherwise.finish()