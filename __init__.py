import os

if not os.environ.get("PYTEST_RUNNING"):
    from . import command, handlers, session  # noqa: F401
    from .config import config  # noqa: F401
