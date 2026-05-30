import asyncio
import random
import uuid

import httpx
from nonebot import get_driver, on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from .auxs import (
    get_forward_nodes,
    get_images_url,
    rm_path,
    send_msg,
    stuff_download,
)
from .commands import *
from .config import config
from .session import BotSession

shitlock = asyncio.Lock()


def get_sub_clses(cls: type):
    registry = []
    for subclass in cls.__subclasses__():
        registry.append(subclass)
    return registry


command_classes = get_sub_clses(BotCommand) + [BotCommand]


async def cmd_handler(
    bot: Bot,
    matcher: type[Matcher],
    event: MessageEvent,
    cmd_cls: type,
    args: Message,
    *,
    only: str | None = None,
    _pid: int | None = None,
):
    if cmd_cls not in command_classes:
        return

    if only is not None and only != event.message_type:
        tip = f"该功能只能在 {only} 下使用"
        if only == "private":
            tip = "该功能只能在私聊中使用"
        if only == "group":
            tip = "该功能只能在群聊中使用"
        await matcher.finish(tip)

    group_id = str(getattr(event, "group_id", "private"))
    if event.message_type == "private":
        group_id = "private"
    user_id = str(event.user_id)
    cmdname = cmd_cls.get_name()

    session = BotSession.make(group_id, user_id)
    command = cmd_cls.make(bot, session, _pid=_pid)

    if _pid is None:
        _pid = session.curpid
    scmd = session.commands.get(_pid)

    if not scmd:
        tip = "未知错误: 会话command字段为None"
        await matcher.finish(tip)

    if not command and scmd.name != cmdname:
        tip = "错误：会话被占用\n"
        tip += f"命令 {scmd.name} 正在运行，进行下一步前请先终止它或等待其完成。"
        await matcher.finish(tip)

    await scmd.run(args)
    await matcher.finish()


def cmd_register(
    name: str,
    cmd_cls: type,
    *,
    only: str | None = None,
    priority: int = 2,
    block: bool = True,
    _pid: int | None = None,
):
    matcher = on_command(name, priority=priority, block=block)

    @matcher.handle()
    async def _handler(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
        await cmd_handler(bot, matcher, event, cmd_cls, args, only=only, _pid=_pid)

    return matcher


driver = get_driver()


@driver.on_startup
async def startup():
    await rm_path(config.cache)
    config.cache.mkdir(parents=True, exist_ok=True)
    logger.info("nonebot-plugin-shitbot 已加载")


@driver.on_shutdown
async def shutdown():
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)


# ===Commands handlers=== #
cmd_session = cmd_register("session", BotCommandSession, priority=1, _pid=0)

cmd_help = cmd_register("help", BotCommandHelp)

cmd_randpic = cmd_register("randpic", BotCommandRandpic)

cmd_advrandpic = cmd_register("advrandpic", BotCommandAdvrandpic)

cmd_convert = cmd_register("convert", BotCommandConvert, only="private")

cmd_shitpost = cmd_register("shitpost", BotCommandShitpost, only="private")

cmd_md2pic = cmd_register("md2pic", BotCommandMd2pic)

cmd_otherwise = cmd_register("", BotCommand, priority=3)

# ===Messages handlers=== #


msg_convert = on_message(priority=10, block=False)


@msg_convert.handle()
async def handle_msg_convert(bot: Bot, event: MessageEvent):
    if event.message_type != "private":
        return
    user_id = str(event.user_id)
    session = BotSession.get_obj("private", user_id)
    if not session:
        return
    if (command := session.commands.get(session.curpid)) is None:
        return
    if not isinstance(command, BotCommandConvert):
        return
    if not command.if_accept_pic:
        return
    lock = command.download_lock
    pid = command.pid
    if lock is None:
        return

    async with lock:
        temp_images_dir = config.cache / "private" / user_id / str(pid) / "temp"
        temp_images_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient() as client:
            url_list = await get_images_url(bot, event.reply, event.get_message(), 5)
            for url in url_list:
                safe_name = f"{uuid.uuid4().hex}"
                save_path = temp_images_dir / safe_name
                try:
                    await stuff_download(client, url, save_path)
                    await command.temp_images.put(str(save_path))
                    logger.info(f"下载图片成功: {save_path}")
                except Exception as e:
                    logger.error(f"下载图片失败 {url}: {e}")
            command.p2png_event.set()


msg_shitpost = on_message(priority=10, block=False)


@msg_shitpost.handle()
async def handle_msg_shitpost(bot: Bot, event: MessageEvent):
    if event.message_type != "private":
        return
    user_id = str(event.user_id)
    session = BotSession.get_obj("private", user_id)
    if not session:
        return
    command = session.commands.get(session.curpid)
    if not command:
        return
    if not isinstance(command, BotCommandShitpost):
        return
    if not command.is_forwardable:
        return
    groups = command.groups
    msg = event.get_message()

    async def _send(group: int, msg: Message, maxtry: int):
        for i in range(maxtry):
            try:
                if not msg:
                    return
                message = msg
                if msg[0].type == "forward":
                    msg_id = msg[0].data.get("id")
                    if msg_id is None:
                        return
                    forward_data = await bot.get_forward_msg(id=msg_id)
                    forward_msgs = forward_data.get("messages", [])
                    message = get_forward_nodes(
                        forward_msgs, config.max_message_depth, summary="喵~"
                    )
                else:
                    for seg in message:
                        seg.data["summary"] = "喵~"
                        if seg.data.get("sub_type", 0) != 0:
                            seg.data["sub_type"] = 1
                    message[-1].data["summary"] = "喵~"
                await send_msg(bot=bot, group_id=group, msg=message)
                return
            except Exception as e:
                if i >= maxtry - 1:
                    logger.error(f"转发失败:{e}")
                    return
                logger.error(f"转发失败，准备第{i + 1}次重试")
                await asyncio.sleep(0.25)

    async with shitlock:
        for group in groups:
            asyncio.create_task(_send(group, msg, 3))
        await asyncio.sleep(random.randint(30, 120))


# Simple auto reply, just for fun :). May be reconstructed in future.
msg_autoreply = on_message(priority=10, block=False)


@msg_autoreply.handle()
async def handle_msg_autoreply(bot: Bot, event: MessageEvent):
    group_id = getattr(event, "group_id", None)
    if event.message_type == "private":
        group_id = None
    user_id = event.user_id
    if group_id is not None:
        user_id = None
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
        if cleaned_text in ["csn", "草死你", "操死你", "🌿死你", "艹死你", "zjsncsn"]:
            wcsn_path = config.client_base / "data" / "wcsn.jpg"
            msg = Message(MessageSegment.image(f"file://{wcsn_path}"))
            msg[0].data["sub_type"] = 1
            msg[0].data["summary"] = "喵呜~"
            await send_msg(bot=bot, group_id=group_id, user_id=user_id, msg=msg)
            return
        cleaned = text.replace("?", "").replace(" ", "").replace("？", "")
        if cleaned in ["这是你吗", "zsnm", "是你吗"]:
            await send_msg(bot=bot, group_id=group_id, user_id=user_id, msg="是我。")
            return
