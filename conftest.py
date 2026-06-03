"""pytest 配置：阻止 __init__.py 的相对导入报错，并提供 sys.path 支持."""

import os
import sys

os.environ["PYTEST_RUNNING"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
