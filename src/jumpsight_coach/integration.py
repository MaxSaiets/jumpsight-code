"""Ports through which the coach service reaches a host application.

The coach package runs on its own. When it is mounted inside the analysis
application, the host registers implementations here with `install`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


def _no_job(_job_id: str) -> dict | None:
    return None


def _no_running_jobs() -> Iterable[tuple[str, dict]]:
    return ()


@dataclass
class Host:
    """What the coach may ask of the host. Defaults describe a host with no analyses."""

    # A live job record by id, or None. The record carries at least "uid".
    find_job: Callable[[str], dict | None] = _no_job
    # (job id, record) for every job the host process holds right now.
    running_jobs: Callable[[], Iterable[tuple[str, dict]]] = _no_running_jobs
    # Whether a derived 3D avatar file is current for its result and video.
    avatar_cache_is_current: Callable[[Path, Path, Path], bool] | None = None
    # Build the 3D avatar for an analysis stem; returns a short status message.
    avatar_generate: Callable[[str], str] | None = None
    # Version stamp written into avatar files by `avatar_generate`.
    avatar_generator_version: int | None = None


HOST = Host()


def install(**ports) -> None:
    """Register host implementations by field name; unknown names are an error."""
    for name, value in ports.items():
        if not hasattr(HOST, name):
            raise TypeError(f"unknown coach port: {name}")
        setattr(HOST, name, value)


def reset() -> None:
    """Return every port to its default (used by tests)."""
    for name, value in vars(Host()).items():
        setattr(HOST, name, value)
