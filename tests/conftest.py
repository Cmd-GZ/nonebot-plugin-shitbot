"""Root conftest: shared setup for all tests (unit + integration)."""

import os
import sys
from pathlib import Path


def pytest_sessionstart(session):
    # Signal the plugin's __init__.py to skip heavy NoneBot-dependent imports.
    # Pure logic modules (parser, aux, etc.) can then be imported without a
    # running NoneBot driver.  Integration tests that actually need the driver
    # will bring it up themselves (see tests/integration/conftest.py).
    os.environ["PYTEST_RUNNING"] = "1"

    # Ensure the plugin package is importable during tests.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
