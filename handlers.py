import asyncio
import httpx

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment, Message
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11.exception import ActionFailed

from .auxiliaries import sendMsg, getImagesUrl, stuffDownload
from .session import BotSession
from .command import *
from .config import getConfig
config = getConfig()


def getSubClses(cls: type):
    registry = []
    for subclass in cls.__subclasses__():
        registry.append(subclass)
    return registry

command_classes = getSubClses(BotCommand) + [BotCommand]

async def cmdHandler(bot: Bot, matcher: type[Matcher], event: MessageEvent, cmd_cls: type, args: Message, *, only: str | None = None):
    if cmd_cls not in command_classes: return

    if only is not None and only != event.message_type:
        tip = f"该功能只能在 {only} 下使用"
        if only == "private": tip = f"该功能只能在私聊中使用"
        if only == "group": tip = f"该功能只能在群聊中使用"
        await matcher.finish(tip)

    group_id = str(getattr(event, 'group_id', "private"))
    if event.message_type == "private": group_id = "private"
    user_id = str(event.user_id)
    cmdname = cmd_cls.getName()

    session = BotSession.make(group_id, user_id)
    command = cmd_cls.make(bot, session, args)

    if not session.command:
        tip = "未知错误: 会话command字段为None"
        await matcher.finish(tip)

    if not command and session.command.name != cmdname:
        tip =  "错误：会话被占用\n"
        tip += f"命令 {session.command.name} 正在运行，进行下一步前请先终止它或等待其完成。"
        await matcher.finish(tip)

    if not command and session.command.name == cmdname:
        await session.command.setArgv(args)

    if not command: await matcher.finish() # Just for making the incorrect error disappear

    await command.run()
    await matcher.finish()

def cmdRegister(name: str, cmd_cls: type, *, only: str | None = None, priority: int = 1, block: bool = True):
    matcher = on_command(name, priority=priority, block=block)

    @matcher.handle()
    async def _handler(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
        await cmdHandler(bot, matcher, event, cmd_cls, args, only=only)

    return matcher


# ===Commands handlers=== #
cmd_help = cmdRegister("help", BotCommandHelp)

cmd_randpic = cmdRegister("randpic", BotCommandRandpic)

cmd_convert = cmdRegister("convert", BotCommandConvert, only="private")

cmd_shitpost = cmdRegister("shitpost", BotCommandShitpost, only="private")

cmd_otherwise = cmdRegister("", BotCommand, priority=2)

# ===Messages handlers=== #


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
        temp_images_dir = config.bot_base / "private" / user_id / "temp"
        temp_images_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient() as client:
            url_list = await getImagesUrl(bot, event.reply, event.get_message(), 5)
            for url in url_list:
                safe_name = f"{uuid.uuid4().hex}"
                save_path = temp_images_dir / safe_name
                try:
                    await stuffDownload(client, url, save_path)
                    await session.command.temp_images.put(str(save_path))
                    logger.info(f"下载图片成功: {save_path}")
                except Exception as e:
                    logger.error(f"下载图片失败 {url}: {e}")
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

    async def _send(group: int, maxtry: int):
        for i in range(maxtry):
            try:
                await bot.send_group_msg(group_id=group, message=event.get_message())
                return
            except ActionFailed as e:
                if i >= maxtry - 1:
                    logger.error(f"转发失败:{e}")
                    return
                logger.error(f"转发失败，准备第{i + 1}次重试")
                await asyncio.sleep(0.25)


    for group in session.command.groups:
        asyncio.create_task(_send(group, 3))


# Simple auto reply, just for fun :). May be reconstructed in fucture.
msg_autoreply = on_message(priority=10, block=False)
@msg_autoreply.handle()
async def handleMsgAutoreply(bot: Bot, event: MessageEvent):
    group_id = getattr(event, 'group_id', "private")
    if event.message_type == "private": group_id = "private"
    user_id = str(event.user_id)

    for seg in event.get_message():
        if seg.type != "text": continue
        text = seg.data.get('text', "")
        if text.replace("!", "").replace(" ", "").replace("！", "").replace("w", "").replace("我", "") in ["csn", "草死你", "操死你", "🌿死你", "艹死你", "zjsncsn"]:
            await sendMsg(bot, group_id, user_id, Message(MessageSegment.image(f"file://{config.client_base / "wcsn.jpg"}")))
            return
        if text.replace("?", "").replace(" ", "").replace("？", "") in ["这是你吗", "zsnm", "是你吗"]:
            await sendMsg(bot, group_id, user_id, "是我。")
            return