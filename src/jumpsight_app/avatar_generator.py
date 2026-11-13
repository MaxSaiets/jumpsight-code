"""3D avatar of the user's own jump (public edition: interface only).

The generator builds a 3D skeleton animation from the engine's pose window.
It depends on the private engine and is not included; the coaching service
sees the avatar as "not available" and says so.
"""

from __future__ import annotations

from pathlib import Path

GENERATOR_VERSION = 3
PRIVATE_NOTE = "3D avatar generation depends on the private analysis engine"


def _cache_is_current(out_f: Path, result_f: Path, video_f: Path) -> bool:
    return False


def generate(stem: str) -> str:
    """Returns a status message; without the engine nothing is generated."""
    return "disabled: " + PRIVATE_NOTE
