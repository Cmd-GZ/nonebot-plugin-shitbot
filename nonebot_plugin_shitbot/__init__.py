from os import environ

# During unit tests, skip importing the heavy handler/command modules.
# These modules pull in the entire NoneBot stack and external plugins
# (e.g. nonebot_plugin_htmlrender → get_driver()).  Pure-logic modules
# like parser.py should remain importable without a running NoneBot.
if not environ.get("PYTEST_RUNNING"):
    from . import handlers  # noqa: F401
