"""Goal for one jump: name, target % of clean attempts, date.

Separate from skills.py: skill_map() computes the current state from the journal, which is a measurement, not an intention. The goal itself is not measured; it is set by a person. Proof of completion is always taken from the journal (skill_map), not from self-report: the goal only stores what and by when, not what "readiness" is in the person's opinion.
"""

from __future__ import annotations

import json
import time

from jumpsight_core.paths import STATE_DIR

STORE = STATE_DIR / "goal.json"


def _sp():
    from .userctx import user_path

    return user_path(STORE)


def load() -> dict | None:
    if not _sp().exists():
        return None
    try:
        return json.loads(_sp().read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save(jump: str, target_pct: float, target_date: str) -> dict:
    # atomically and under a lock (statefile.py): a plain write_text interrupted midway leaves an empty file, and
    # two consecutive saves would overwrite each other
    from .statefile import update_json

    d = {"jump": jump, "target_pct": target_pct, "target_date": target_date, "created_ts": time.time()}
    update_json(_sp(), lambda _cur: d, None)
    return d


def clear() -> None:
    if _sp().exists():
        _sp().unlink()


def with_progress(lang: str = "en") -> dict | None:
    """Goal + current state from the journal. None if no goal is set."""
    g = load()
    if not g:
        return None
    from .skills import skill_map

    jumps = skill_map(lang).get("jumps") or []
    row = next((j for j in jumps if j["jump"] == g["jump"]), None)
    current_pct = row["clean_pct"] if row else None
    attempts = row["attempts"] if row else 0
    assessed = row.get("clean_assessed_total", attempts) if row else 0
    clean = row["clean"] if row else 0
    return {
        **g,
        "current_pct": current_pct,
        "attempts": attempts,
        "clean_assessed_total": assessed,
        "clean": clean,
        "progress_pct": min(100, round(100 * current_pct / g["target_pct"]))
        if current_pct is not None and g["target_pct"]
        else None,
    }
