"""Session journal: storage, completion records, drill outcome streaks and recency."""

from __future__ import annotations

import json
import re
import time
from contextvars import ContextVar

from jumpsight_core.paths import STATE_DIR

from ..core import load_kb

LOG = STATE_DIR / "session_log.json"


def _lp():
    from ..userctx import user_path

    return user_path(LOG)


# Hypothetical sessions for the multi-day forecast: the journal can be temporarily supplemented with assumed
# sessions, so the same engine that builds one day unfolds the plan further. The assumption is stated in every
# day: days after the nearest one are a forecast, rebuilt as soon as a real result appears.
_SIM: ContextVar[tuple[dict, ...]] = ContextVar("coach_forecast", default=())


def _log() -> list[dict]:
    real = json.loads(_lp().read_text(encoding="utf-8")) if _lp().exists() else []
    return real + list(_SIM.get())


def _outcome_streaks(rows: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    """Series of self-ratings, not confirmation that a skill is mastered.

    One session gives at most one result per drill. In contradictory legacy
    duplicates, fail/partial/unrated outweigh ok; order does not matter.
    """
    sessions: dict[tuple, list[dict]] = {}
    for index, row in enumerate(rows):
        sid = row.get("session_id")
        key = ("id", sid) if sid else ("row", index)
        sessions.setdefault(key, []).extend(row.get("blocks", []))
    success, failure = {}, {}
    priority = {"ok": 0, "done": 1, "partial": 2, "fail": 3}
    for blocks in sessions.values():
        outcomes = {}
        for block in blocks:
            did = block.get("drill_id")
            if not did:
                continue
            result = block.get("outcome", "done")
            if result not in priority:
                result = "done"
            previous = outcomes.get(did, "ok")
            outcomes[did] = max((previous, result), key=priority.get)
        for did, result in outcomes.items():
            success[did] = success.get(did, 0) + 1 if result == "ok" else 0
            failure[did] = failure.get(did, 0) + 1 if result == "fail" else 0
    return success, failure


def _save(entry: dict) -> None:
    # Only real entries are written: _log() can contain assumed sessions.
    from ..statefile import update_json

    def _mut(cur):
        data = list(cur or [])
        sid = entry.get("session_id")
        if sid:
            previous = next((row for row in data if row.get("session_id") == sid), None)
            if previous is not None:
                fields = ("focus", "note", "effort", "blocks")
                if any(previous.get(k, "" if k != "blocks" else []) != entry[k] for k in fields):
                    raise ValueError("session id conflict")
                return data
        data.append(entry)
        return data

    update_json(_lp(), _mut, [])


def _recent_drill_ids(n: int = 3) -> list[str]:
    """Drills of the last n sessions, so the same ones are not given every day."""
    out = []
    for s in _log()[-n:]:
        out += [b["drill_id"] for b in s.get("blocks", []) if b.get("drill_id")]
    return out


def _last_used() -> dict[str, int]:
    """Drill id -> session number when it was last given.

    Sorted by age, the longest unused first: sorting by the number of mentions failed when the available drills were
    exactly what a day needs, because everyone had the same score and day 2 came out as a copy of day 1.
    """
    seen: dict[str, int] = {}
    for i, s in enumerate(_log()):
        for b in s.get("blocks", []):
            if b.get("drill_id"):
                seen[b["drill_id"]] = i
    return seen


def complete(
    done_ids: list[str],
    focus: str,
    note: str = "",
    outcomes: dict | None = None,
    effort: str = "",
    session_id: str = "",
) -> dict:
    """Records what the user did and HOW it went, to the journal.

    To advance a rung the next session must know the result. outcomes: {drill_id: "ok" | "partial" | "fail"}, optional
    (without it the drill is counted as performed).
    """
    outcomes = outcomes or {}
    if effort not in ("", "easy", "right", "much"):
        raise ValueError("invalid effort")
    if session_id and (len(session_id) > 80 or not re.fullmatch(r"[A-Za-z0-9_-]+", session_id)):
        raise ValueError("invalid session id")
    if any(v not in ("ok", "partial", "fail", "done") for v in outcomes.values()):
        raise ValueError("invalid drill outcome")
    done_ids = list(dict.fromkeys(done_ids))
    drills, _ = load_kb()
    known = {d["id"] for d in drills if d.get("kind") != "do_not_recommend" and not d.get("do_not_recommend")}
    if any(i not in known for i in done_ids):
        raise ValueError("unknown drill")
    if any(i not in done_ids for i in outcomes):
        raise ValueError("outcome without completed drill")
    entry = {
        "ts": time.time(),
        "focus": focus,
        "note": note,
        "effort": effort,
        "session_id": session_id,
        "blocks": [{"drill_id": i, "outcome": outcomes.get(i, "done")} for i in done_ids],
    }
    _save(entry)
    return {"ok": True, "sessions": len(_log())}


def history() -> list[dict]:
    return list(reversed(_log()))[:20]
