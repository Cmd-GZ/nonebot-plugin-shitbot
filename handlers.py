import asyncio
import httpx

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, MessageSegment, Message
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.log import logger

from .auxiliaries import imagesDownload
from .session import BotSession
from .tasks import convertP2Png
from .command import *
from .config import getConfig
config = getConfig()


# ===Commands handlers=== #
cmd_help = on_command("help", priority=1, block=True)
@cmd_help.handle()
async def handleCmdHelp(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if event.message_type != "private": return
    session = BotSession.make("private", str(event.user_id))
    command = BotCommandHelp.make(bot, session, args)
    if not session.command:
        tip = "未知错误: 会话command字段为None"
        await cmd_help.finish(tip)
    if not command:
        tip =  "错误：会话被占用\n"
        tip += f"命令 {session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
        await cmd_help.finish(tip)

    await command.run()
    await cmd_help.finish()

cmd_randpic = on_command("randpic", priority=1, block=True)
@cmd_randpic.handle()
async def handleRandpic(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    group_id = getattr(event, 'group_id', "private")
    if event.message_type == "private": group_id = "private"
    session = BotSession.make(str(group_id), str(event.user_id))
    command = BotCommandRandpic.make(bot, session, args)
    if not session.command:
        tip = "未知错误: 会话command字段为None"
        await cmd_randpic.finish(tip)
    if not command:
        tip =  "错误：会话被占用\n"
        tip += f"命令 {session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
        await cmd_randpic.finish(tip)

    await command.run()
    await cmd_randpic.finish()

cmd_convert = on_command("convert", priority=1, block=True)
@cmd_convert.handle()
async def handleCmdConvert(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if event.message_type != "private": return
    session = BotSession.make("private", str(event.user_id))
    command = BotCommandConvert.make(bot, session, args)
    if not session.command:
        tip = "未知错误: 会话command字段为None"
        await cmd_convert.finish(tip)
    if not command and session.command.name != "convert":
        tip =  "错误：会话被占用\n"
        tip += f"命令 {session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
        await cmd_convert.finish(tip)

    if not command and session.command.name == "convert":
        await session.command.setArgv(args)

    if not command: await cmd_convert.finish() # Just for making the incorrect error disappear

    await command.run()
    await cmd_convert.finish()

cmd_shitpost = on_command("shitpost", priority=2, block=True)
@cmd_shitpost.handle()
async def handleShitpost(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if event.message_type != "private": return
    session = BotSession.make("private", str(event.user_id))
    command = BotCommandShitpost.make(bot, session, args)
    if not session.command:
        tip = "未知错误: 会话command字段为None"
        await cmd_shitpost.finish(tip)
    if not command and session.command.name != "shitpost":
        tip =  "错误：会话被占用\n"
        tip += f"命令 {session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
        await cmd_shitpost.finish(tip)

    if not command and session.command.name == "shitpost":
        await session.command.setArgv(args)

    if not command: await cmd_shitpost.finish() # Just for making the incorrect error disappear

    await command.run()
    await cmd_shitpost.finish()

cmd_otherwise = on_command("", priority=2, block=True)
@cmd_otherwise.handle()
async def handleCmdOtherwise(bot: Bot, event: MessageEvent):
    if event.message_type != "private": return
    session = BotSession.make("private", str(event.user_id))
    command = BotCommand.make(bot, session)
    if not session.command:
        tip = "未知错误: 会话command字段为None"
        await cmd_help.finish(tip)
    if not command:
        tip =  "错误：会话被占用\n"
        tip += f"命令 {session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
        await cmd_otherwise.finish(tip)

    await command.run()
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
    if not session.command.if_accept_pic: return
    lock = session.command.download_lock
    if lock is None: return

    async with lock:
        temp_images_dir = config.temp_dir / user_id
        temp_images_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient() as client:
            await imagesDownload(bot, event.reply, event.get_message(), client, temp_images_dir, session.command.temp_images, user_id, 5)
            session.command.p2png_event.set()


msg_shitpost = on_message(priority=10, block=False)
@msg_shitpost.handle()
async def handleMsgShitpost(bot: Bot, event: MessageEvent):
    if event.message_type != "private": return
    user_id = str(event.user_id)
    session = BotSession.getObj("private", user_id)
    if not session: return
    if not session.command: return
    if not isinstance(session.command, BotCommandShitpost): return
    if not session.command.is_forwardable: return

    for group in session.command.groups:
        await bot.send_group_msg(group_id=group, message=event.get_message())