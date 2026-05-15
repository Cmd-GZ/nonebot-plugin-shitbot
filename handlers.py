import asyncio

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.log import logger

from .auxiliaries import imagesDownload
from .session import BotSession
from .command import BotCommand, BotCommandHelp, BotCommandConvert
from .config import getConfig
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
        await cmd_help.finish(tip)

    await command.run(bot)
    await cmd_otherwise.finish()

cmd_convert = on_command("convert", priority=2, block=True)
@cmd_convert.handle()
async def handleCmdConvert(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if event.message_type != "private": return
    session = BotSession.make("private", str(event.user_id))
    command = BotCommandConvert.make(session, args)
    if not command and session.command != "convert":
        tip =  "错误：会话被占用\n"
        tip += f"命令 {session.command} 正在运行，进行下一步前请先终止它或等待其完成。"
        await cmd_convert.finish(tip)

    if not command and session.command == "convert":
        await session.command.setArgv(args, bot)

    if not command: await cmd_convert.finish() # Just for making the incorrect error disappear

    await command.run(bot)
    await cmd_convert.finish()

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
    await cmd_help.finish()





msg_convert = on_message(priority=10, block=False)
@msg_convert.handle()
async def handleMsgConvert(bot: Bot, event: MessageEvent):
    if event.message_type != "private": return
    user_id = str(event.user_id)
    session = BotSession.getObj("private", user_id)
    if not session: return
    if not session.command: return
    if not isinstance(session.command, BotCommandConvert): return
    lock = session.command.lock
    if lock is None: return

    async with lock:
        if not session.command.name == "convert": return

        temp_images_dir = config.temp_dir / user_id
        temp_images_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient() as client:
            await imagesDownload(bot, event.reply, event.get_message(), client, temp_images_dir, user_id, 5)