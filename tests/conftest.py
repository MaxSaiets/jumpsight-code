"""Shared pytest setup.

Tests that need model weights, media files or recorded caches skip with a
reason instead of failing; the markers are declared in pyproject.toml.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

# Mutable state (jobs, accounts, analysis output) goes to a throw-away directory;
# jumpsight_core.paths reads this at import time, so it must be set first.
os.environ.setdefault("JS_VAR_DIR", tempfile.mkdtemp(prefix="js_tests_"))

from jumpsight_core import paths  # noqa: E402


def pytest_collection_modifyitems(config, items):
    """Apply `requires_models` / `requires_media` skips from the environment."""
    ffmpeg = shutil.which("ffmpeg") and shutil.which("ffprobe")
    models_present = paths.MODELS_DIR.is_dir() and any(paths.MODELS_DIR.iterdir())
    for item in items:
        if "requires_media" in item.keywords and not ffmpeg:
            item.add_marker(pytest.mark.skip(reason="ffmpeg/ffprobe are not on PATH"))
        if "requires_models" in item.keywords and not models_present:
            item.add_marker(pytest.mark.skip(reason=f"no model weights in {paths.MODELS_DIR} (see models/MANIFEST.md)"))
