import asyncio

import yaml
from nonebot import get_driver, on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from .aux import rm_path
from .commands import *
from .config import config
from .msgutils import get_reply
from .session import BotSession


def collect_class_hierarchy(cls: type):
    registry = [cls]
    for subclass in cls.__subclasses__():
        registry.append(subclass)
        registry.extend(collect_class_hierarchy(subclass))
    return registry


command_classes = collect_class_hierarchy(BotCommand)


async def cmd_handler(
    bot: Bot,
    matcher: type[Matcher],
    event: MessageEvent,
    cmd_cls: type,
    args: Message,
    *,
    _pid: int | None = None,
):
    if cmd_cls not in command_classes:
        return

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

    reply = get_reply(event)
    if reply is not None:
        args = Message([reply]) + args
    await scmd.run(args)
    await matcher.finish()


def cmd_register(
    name: str,
    cmd_cls: type,
    *,
    priority: int = 2,
    block: bool = True,
    _pid: int | None = None,
):
    matcher = on_command(name, priority=priority, block=block)

    async def _handler(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
        await cmd_handler(bot, matcher, event, cmd_cls, args, _pid=_pid)

    matcher.handle()(_handler)

    return matcher


driver = get_driver()


@driver.on_startup
async def startup():
    await rm_path(config.cache)
    config.cache.mkdir(parents=True, exist_ok=True)
    logger.info("nonebot-plugin-shitbot 已加载")


@driver.on_bot_connect
async def bot_connect(bot: Bot):
    autoreply_auto_path = config.data / "autoreply" / "state.yaml"
    if autoreply_auto_path.exists():
        is_auto = yaml.safe_load(autoreply_auto_path.read_text(encoding="utf-8"))
        if is_auto == False:  # is_auto is None means True
            return
    session = BotSession.make("public", "autoreply")
    autoreply_main = BotCommandAutoReplyMain.make(bot, session, _pid=session.curpid)
    if autoreply_main is None:
        return
    await autoreply_main.run(Message())


@driver.on_shutdown
async def shutdown():
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)


# ===Commands handlers=== #
cmd_session = cmd_register("session", BotCommandSession, priority=1, _pid=0)

cmd_perm = cmd_register("perm", BotCommandPerm)

cmd_help = cmd_register("help", BotCommandHelp)

cmd_randpic = cmd_register("randpic", BotCommandRandpic)

cmd_pixiv = cmd_register("pixiv", BotCommandPixiv)

cmd_advrandpic = cmd_register("advrandpic", BotCommandAdvrandpic)

cmd_convert = cmd_register("convert", BotCommandConvert)

cmd_shitpost = cmd_register("shitpost", BotCommandShitpost)

cmd_md2pic = cmd_register("md2pic", BotCommandMd2pic)

cmd_autoreply = cmd_register("autoreply", BotCommandAutoreply)

cmd_otherwise = cmd_register("", BotCommand, priority=3)

# ===Messages handlers=== #

msg_manager = on_message(priority=10, block=False)


@msg_manager.handle()
async def handle_msg_manager(event: MessageEvent):
    group_id = str(getattr(event, "group_id", "private"))
    if event.message_type == "private":
        group_id = "private"
    user_id = str(event.user_id)
    sessions = BotSession.get_group_objs("public")
    session = BotSession.get_obj(group_id, user_id)
    if session is not None:
        sessions.append(session)
    for session in sessions:
        if (command := session.commands.get(session.curpid)) is None:
            continue
        await command.roger(event)
