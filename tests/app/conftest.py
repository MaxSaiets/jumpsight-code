"""Shared setup for the app tests.
This directory is put on `sys.path` so tests can import sibling helpers by name.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


@pytest.fixture(autouse=True)
def _coach_host():
    """tests/app exercise the integrated system: the app is the coach's host."""
    from jumpsight_app import coach_host
    from jumpsight_coach import integration

    coach_host.install()
    yield
    integration.reset()
