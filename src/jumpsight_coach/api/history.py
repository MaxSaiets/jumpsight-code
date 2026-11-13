"""Attempt journal and progress routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..core import load_kb

router = APIRouter()


@router.get("/history")
def get_history(lang: str = "en") -> list[dict]:
    """Attempt journal."""
    from ..jobs import history, rev_is_usable

    rows = history()
    # The server decides whether the revolution count is usable, the same way for every record;
    # the client must not invent its own rule.
    for r in rows:
        r["rev_usable"] = rev_is_usable(r)
    return rows


@router.get("/progress")
def get_progress() -> dict:
    from ..jobs import progress

    return progress()


@router.get("/progress_goals")
def get_progress_goals(lang: str = "en") -> dict:
    """Close the loop "drill → repeat video → did it improve" PER GOAL,
    not only per jump overall.

    streak_days: consecutive days with a completed session (today or yesterday counts as a live streak); sessions_7d: sessions in the last 7 days; goals: for each KB goal, how many sessions had this focus and whether the corresponding error became rarer in the latest analyses compared with earlier ones.
    A trend needs at least 3 assessed checks of the goal on each side, from one engine, and a session with this goal between the samples.
    """
    import time as _t

    from ..core import CODE_ALIASES
    from ..jobs import _load_hist, goal_check_state
    from ..session import _log as _sess_log
    from ..session import goal_label

    now = _t.time()
    sessions = [s for s in _sess_log() if isinstance(s, dict) and s.get("ts")]
    days = sorted({_t.strftime("%Y-%m-%d", _t.localtime(s["ts"])) for s in sessions})
    today = _t.strftime("%Y-%m-%d", _t.localtime(now))
    yest = _t.strftime("%Y-%m-%d", _t.localtime(now - 86400))
    streak = 0
    if days and days[-1] in (today, yest):
        cur = days[-1]
        dset = set(days)
        while cur in dset:
            streak += 1
            cur = _t.strftime("%Y-%m-%d", _t.localtime(_t.mktime(_t.strptime(cur, "%Y-%m-%d")) - 86400))
    sessions_7d = sum(1 for s in sessions if s["ts"] >= now - 7 * 86400)
    # goal <- analyzer error codes
    goal_codes: dict[str, set] = {}
    for code, goal in CODE_ALIASES.items():
        goal_codes.setdefault(goal, set()).add(code)
    for g in ("fall", "two_foot_landing", "stiff_landing_knee", "under_rotation", "axis_tilt", "late_check_out"):
        goal_codes.setdefault(g, set()).add(g)
    hist = [h for h in _load_hist() if h.get("outcome") != "not_measured" and isinstance(h.get("errors"), list)]
    hist.sort(key=lambda h: h.get("ts") or 0)
    # Trend is taken by time and by work between samples, not by record index: "now" is the last
    # TREND_WINDOW_D days and "before" the same number of days preceding them, with at least one
    # completed session between them and at least 3 analyses in each sample. Comparing two halves
    # of one upload session (measured: 6 videos in 2 minutes gave "better" and "worse" at once)
    # is not a trend. Otherwise trend = "n/a" with the reason written out.
    TREND_WINDOW_D = 7
    last_ts = (hist[-1].get("ts") or now) if hist else now
    cut = last_ts - TREND_WINDOW_D * 86400
    recent = [h for h in hist if (h.get("ts") or 0) > cut]
    earlier = [h for h in hist if cut - TREND_WINDOW_D * 86400 < (h.get("ts") or 0) <= cut]
    _, causes = load_kb()
    out_goals = []
    for goal, codes in goal_codes.items():
        n_sess = sum(1 for s in sessions if (s.get("focus") or "") == goal)
        last_ts = max([s["ts"] for s in sessions if (s.get("focus") or "") == goal] or [0])

        # Foot and hand contact are independent signals. The other groups contain
        # alternative codes of the training proxy from different engines.
        def _assessed(rows, codes=codes, goal=goal):
            return [
                (h, state)
                for h in rows
                if (state := goal_check_state(h, codes, require_all=goal == "landing_stability")) is not None
            ]

        rec, old = _assessed(recent), _assessed(earlier)
        r_rec = sum(state for _, state in rec) / len(rec) if rec else None
        r_old = sum(state for _, state in old) / len(old) if old else None
        first_recent = min([h.get("ts") or 0 for h, _ in rec] or [last_ts])
        last_earlier = max([h.get("ts") or 0 for h, _ in old] or [0])
        sessions_between = (
            sum(1 for s in sessions if last_earlier < s["ts"] < first_recent and s.get("focus") == goal)
            if rec and old
            else 0
        )
        engines = {h.get("engine") or "legacy" for h, _ in rec + old}
        if len(rec) < 3 or len(old) < 3:
            trend_reason = "too_few"
        elif len(engines) > 1:
            trend_reason = "mixed_engines"
        elif sessions_between < 1:
            trend_reason = "no_session_between"
        else:
            trend_reason = None
        if trend_reason is None and r_rec is not None and r_old is not None:
            trend = "better" if r_rec < r_old - 0.15 else "worse" if r_rec > r_old + 0.15 else "same"
        else:
            trend = "n/a"
        seen_any = any(set(h["errors"]) & codes for h in hist) or n_sess > 0
        if not seen_any:
            continue
        out_goals.append(
            {
                "goal": goal,
                "sessions": n_sess,
                "last_ts": last_ts,
                "err_rate_recent": None if r_rec is None else round(r_rec, 2),
                "err_rate_earlier": None if r_old is None else round(r_old, 2),
                "n_recent": len(rec),
                "n_earlier": len(old),
                "trend": trend,
                "trend_reason": trend_reason,
                "window_days": TREND_WINDOW_D,
                "sessions_between": sessions_between,
                "title": goal_label(goal),
            }
        )
    out_goals.sort(key=lambda g: (-g["sessions"], g["goal"]))
    return {
        "streak_days": streak,
        "sessions_7d": sessions_7d,
        "sessions_total": len(sessions),
        "last_session_ts": max([s["ts"] for s in sessions] or [0]),
        "analyses_recent": len(recent),
        "goals": out_goals,
    }
