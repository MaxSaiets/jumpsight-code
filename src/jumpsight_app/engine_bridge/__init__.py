"""Interface to the analysis engine (public edition).

The analysis engine — finding the jump, take-off and landing, revolution
counting, jump naming, landing checks — and the code that turns its report
into the app's summary are private and not part of this repository.

This module keeps the interface the web app calls, so the app, its job
queue, uploads, live recording and the coaching service can be read and run.
Without the engine `available()` is False and an analysis job ends with the
honest error ``ENGINE_UNAVAILABLE`` instead of a made-up result.

What the engine returns (every value is a measurement object):

    {
      "value":      2.0 | "Lutz" | null,
      "status":     "measured" | "degraded" | "inferred" | "absent",
      "confidence": "high" | "medium" | "low",
      "method":     "<how it was obtained>",
      "reason":     "<why it is degraded or absent>"
    }

A value the frames do not support is ``absent`` with a reason; the app never
replaces it with a plausible number.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

PRIVATE_NOTE = (
    "the analysis engine is private and not included in the public edition "
    "of this repository; see README.md, 'Access to the full source'"
)


class EngineUnavailable(RuntimeError):
    """Raised by every call that needs the private engine."""


def available() -> bool:
    """True when the engine can be started. Always False in the public edition."""
    return False


def unavailable_reason() -> str:
    return PRIVATE_NOTE


def run_with_focus_snapshot(fn: Callable[[], Any]) -> Any:
    """Run `fn` with the user's training focus applied to the engine's priors.
    Without the engine there is nothing to apply, so `fn` runs as is."""
    return fn()


def warm_worker() -> None:
    """Start the long-lived engine worker process ahead of the first job."""
    raise EngineUnavailable(PRIVATE_NOTE)


def run(video: str, **kwargs: Any) -> dict | None:
    """Analyse a whole video; returns the engine report or None."""
    raise EngineUnavailable(PRIVATE_NOTE)


def run_streaming(video: str, on_event: Callable[[dict], None], scan_path: str | None = None) -> dict | None:
    """Analyse a video and call `on_event` for progress events
    ("media.probe", "scan.done", "candidate.found", "attempt.done", ...)."""
    raise EngineUnavailable(PRIVATE_NOTE)


def to_summary_jumps(report: dict, **kwargs: Any) -> list[dict]:
    """Engine report -> rows of /summary (one per attempt)."""
    raise EngineUnavailable(PRIVATE_NOTE)


def to_result(report: dict, **kwargs: Any) -> dict:
    """Engine report -> full per-attempt result for the answer screen."""
    raise EngineUnavailable(PRIVATE_NOTE)


def public_jump_view(row: dict) -> dict:
    """The subset of an attempt that is safe to show to the user."""
    raise EngineUnavailable(PRIVATE_NOTE)


def skater_track(report: dict) -> list | None:
    """Bounding boxes of the skater for the close-up player."""
    return None


def verify_declared(declared: str, row: dict) -> dict:
    """Compare the jump the user declared with what was measured."""
    raise EngineUnavailable(PRIVATE_NOTE)


def verify_declared_turns(declared_turns: str, row: dict) -> dict:
    """Compare the declared number of revolutions with the measured count."""
    raise EngineUnavailable(PRIVATE_NOTE)
