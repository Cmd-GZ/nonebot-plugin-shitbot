from os import environ

# During unit tests, skip importing the heavy handler/command modules.
# These modules pull in the entire NoneBot stack and external plugins
# (e.g. nonebot_plugin_htmlrender → get_driver()).  Pure-logic modules
# like parser.py should remain importable without a running NoneBot.
if not environ.get("PYTEST_RUNNING"):
    from nonebot.plugin import PluginMetadata

    from . import handlers  # noqa: F401

    __plugin_meta__ = PluginMetadata(
        name="shitbot",
        description="个人自用自己手搓框架的多功能bot, 还在开发中",
        usage="发送/help 查看帮助信息",
        type="application",
        homepage="https://github.com/Cmd-GZ/nonebot-plugin-shitbot",
        supported_adapters={"~onebot.v11"},
    )
