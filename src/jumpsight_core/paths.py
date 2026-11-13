"""Filesystem locations used across the platform.

Every location can be overridden with an environment variable, so a deployment
never depends on where the repository happens to be checked out. Mutable state
(uploads, accounts, analysis output) lives outside the source tree.
"""

from __future__ import annotations

import os
from pathlib import Path


def _from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


REPO_ROOT = Path(__file__).resolve().parents[2]

VAR_DIR = _from_env("JS_VAR_DIR", REPO_ROOT / "var")
MODELS_DIR = _from_env("JS_MODELS_DIR", REPO_ROOT / "models")
OUTPUT_DIR = _from_env("JS_OUTPUT_DIR", VAR_DIR / "output")
STATE_DIR = _from_env("JS_STATE_DIR", VAR_DIR / "state")
WORK_DIR = _from_env("JS_WORK_DIR", VAR_DIR / "jobs")

WEB_DIR = _from_env("JS_WEB_DIR", REPO_ROOT / "web")
KB_DIR = _from_env("JS_KB_DIR", Path(__file__).resolve().parents[1] / "jumpsight_coach" / "kb")

LESSON_LIBRARY_DIR = _from_env("JS_LESSON_LIBRARY_DIR", VAR_DIR / "lesson_library")
MASCOT_WORK_DIR = _from_env("JS_MASCOT_WORK_DIR", VAR_DIR / "mascot")
