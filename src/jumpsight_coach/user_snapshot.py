"""Everything about the current user for the chat: fresh data, in English.

Requirement: 'the chat must know everything about the user and everything they did, even a minute ago'. Here: a snapshot from the same sources as the screens (analysis journal, day plan, sessions, progress, coach), and instant deterministic answers to frequent personal questions. Numbers come only from the journal; nothing is invented. Only the data of the current uid (all sources read current_uid()).
"""

from __future__ import annotations

import datetime as _dt
import re
import time

_COUNT_EN = {"single": "single", "double": "double", "triple": "triple", "quad": "quad"}
_ERR_EN = {
    "fall": "fall",
    "two_foot_landing": "two-foot landing",
    "step_out": "step-out",
    "touch_down": "free-foot touch down",
    "hand_down": "hand down",
    "tilted_axis": "tilted air axis",
    "stiff_landing_knee": "stiff landing knee",
    "under_rotation": "under-rotation",
}


def _when(ts) -> str:
    try:
        d = _dt.datetime.fromtimestamp(float(ts))
    except (TypeError, ValueError, OSError):
        return "unknown time"
    now = _dt.datetime.now()
    mins = (now - d).total_seconds() / 60
    if mins < 1.5:
        return "just now"
    if mins < 60:
        return f"{int(mins)} min ago"
    if d.date() == now.date():
        return "today " + d.strftime("%H:%M")
    if (now.date() - d.date()).days == 1:
        return "yesterday " + d.strftime("%H:%M")
    return d.strftime("%b %d %H:%M")


def _jump_line(r: dict) -> str:
    """One analysis in words: the same quantities as on the answer screen."""
    name = r.get("name_display") or r.get("jump") or "jump (name not resolved)"
    cnt = _COUNT_EN.get(str(r.get("count_named") or ""), r.get("count_named"))
    parts = [f"{(cnt + ' ') if cnt else ''}{name}".strip()]
    if isinstance(r.get("revolutions"), (int, float)):
        b = r.get("band")
        parts.append(
            f"{r['revolutions']:.2f}"
            + (f" ±{float(b):.2f}" if isinstance(b, (int, float)) else "")
            + " turns in the air"
        )
    if isinstance(r.get("air_time_s"), (int, float)):
        parts.append(f"air time {r['air_time_s']:.2f} s")
    if isinstance(r.get("height_m"), (int, float)):
        parts.append(f"height {r['height_m'] * 100:.0f} cm")
    errs = [_ERR_EN.get(e, e.replace("_", " ")) for e in (r.get("errors") or [])]
    if errs:
        parts.append("errors: " + ", ".join(errs))
    elif r.get("outcome") == "measured" and r.get("errors_checked_clean"):
        parts.append("no errors found")
    return " · ".join(parts)


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def snapshot() -> dict:
    """Snapshot of the current user. Each source separately: a failure of one does not break the rest."""
    from . import jobs as _jobs

    hist = _safe(lambda: [r for r in _jobs.history() if r.get("outcome") != "not_measured"], [])
    out: dict = {"history": hist, "taken_at": time.time()}
    out["me"] = _safe(lambda: __import__("jumpsight_coach.api", fromlist=["acc_me"]).acc_me(), {})
    out["level"] = _safe(lambda: __import__("coach.skills", fromlist=["profile"]).profile("en"), {})
    out["today"] = _safe(lambda: __import__("jumpsight_coach.api", fromlist=["today"]).today(lang="en"), {})
    out["sessions"] = _safe(lambda: __import__("jumpsight_coach.api", fromlist=["sessions"]).sessions(), [])
    out["progress"] = _safe(
        lambda: __import__("jumpsight_coach.api", fromlist=["get_progress_goals"]).get_progress_goals("en"), {}
    )
    out["coach_comment"] = _safe(
        lambda: __import__("jumpsight_coach.api", fromlist=["acc_coach_comment"]).acc_coach_comment().get("comment"),
        None,
    )
    out["running"] = _safe(_running_jobs, [])
    return out


def _running_jobs() -> list[dict]:
    """Analysis computed right now (the same process that serves /status)."""
    from .integration import HOST
    from .userctx import current_uid

    uid = current_uid()
    return [
        {"job": k, "state": v.get("state"), "stage": v.get("stage")}
        for k, v in HOST.running_jobs()
        if v.get("uid") == uid and v.get("state") in ("queued", "scanning", "running")
    ]


def context_text(snap: dict | None = None) -> str:
    """Snapshot as one text for the LLM (source [ME])."""
    s = snap or snapshot()
    lines = []
    me = s.get("me") or {}
    if me:
        lines.append(
            f"USER: {me.get('name') or 'guest'}, role {me.get('role') or 'skater'}"
            + (", signed in" if me.get("signed_in") or me.get("google") else ", guest")
        )
    lv = s.get("level") or {}
    lines.append(
        f"LEVEL: {lv.get('level_name')} (basis: {lv.get('basis')})"
        if lv.get("level")
        else "LEVEL: not determined yet (needs 2 analysed videos with a rotation count)"
    )
    hist = s.get("history") or []
    lines.append(f"ANALYSED JUMPS: {len(hist)}")
    for r in hist[:15]:
        lines.append(f"- {_when(r.get('ts'))}: {_jump_line(r)}")
    for j in s.get("running") or []:
        lines.append(f"ANALYSIS IN PROGRESS NOW: stage {j.get('stage') or j.get('state')}")
    t = s.get("today") or {}
    if t.get("focus_label"):
        drills = [b.get("name") for b in (t.get("blocks") or []) if b.get("drill_id")]
        lines.append(f"TODAY'S SESSION: focus {t['focus_label']}; drills: {', '.join(drills)}")
    ses = s.get("sessions") or []
    if ses:
        last = ses[0] if isinstance(ses, list) else {}
        lines.append(f"COMPLETED SESSIONS: {len(ses)}; last {_when(last.get('ts'))}")
    pg = s.get("progress") or {}
    if pg.get("streak_days") is not None:
        lines.append(f"STREAK: {pg.get('streak_days')} days; sessions in 7 days: {pg.get('sessions_7d')}")
    if s.get("coach_comment"):
        c = s["coach_comment"]
        lines.append(f"COACH COMMENT: {c.get('text') if isinstance(c, dict) else c}")
    return "\n".join(lines)


_MINE = re.compile(r"\b(my|me|mine|i|i've|i'm|did i|have i)\b")


def personal_answer(question: str) -> dict | None:
    """Instant answer to a frequent personal question, from the journal, without an LLM."""
    q = question.lower().strip()
    # «How many falls this week?»: personal, and without the word 'my'
    counting = re.search(
        r"\bhow many\b[^?]*\b(falls?|jumps?|errors?|mistakes?|analys\w*|videos?|sessions?)\b"
        r"[^?]*\b(today|this week|so far|in total|last \d+ days)\b",
        q,
    )
    if not _MINE.search(q) and not counting:
        return None
    s = snapshot()
    hist = s.get("history") or []
    src = [{"source": "your analyses and sessions", "url": "", "score": 1.0}]

    def done(text):
        return {"answer": text, "grounded": True, "structured": "personal_data", "sources": src}

    if re.search(r"\b(last|latest|recent|previous)\b[^?]*\b(jump|analys|video|attempt|result)", q) or re.search(
        r"\bhow was my (last )?jump", q
    ):
        if not hist:
            return done(
                "You have no analysed jumps yet. Upload a jump video on the Analyse tab and the "
                "result will show here right away."
            )
        r = hist[0]
        return done(f"Your latest analysed jump ({_when(r.get('ts'))}): {_jump_line(r)}.")
    if (
        re.search(r"\b(today|this morning|this evening)\b", q)
        and re.search(r"\b(did|done|do|have|my)\b", q)
        and not re.search(r"\b(plan|session|training|workout|why)\b", q)
    ):
        d0 = _dt.datetime.combine(_dt.date.today(), _dt.time()).timestamp()
        tj = [r for r in hist if float(r.get("ts") or 0) >= d0]
        ses = [x for x in (s.get("sessions") or []) if float((x or {}).get("ts") or 0) >= d0]
        lines = [f"Today you analysed {len(tj)} jump{'s' if len(tj) != 1 else ''}" + (":" if tj else ".")]
        lines += [f"• {_when(r.get('ts'))}: {_jump_line(r)}" for r in tj[:8]]
        lines.append(f"Training sessions completed today: {len(ses)}.")
        if s.get("running"):
            lines.append("One analysis is running right now — it will appear here as soon as it is done.")
        return done("\n".join(lines))
    if re.search(r"\bhow many\b", q) or re.search(r"\b(count|number of)\b", q):
        week = time.time() - 7 * 86400
        wk = [r for r in hist if float(r.get("ts") or 0) >= week]
        falls = sum(1 for r in wk if "fall" in (r.get("errors") or []))
        if re.search(r"\bfall", q):
            return done(f"Falls in your analysed jumps over the last 7 days: {falls} of {len(wk)} jumps.")
        if re.search(r"\b(error|mistake)", q):
            n = sum(len(r.get("errors") or []) for r in wk)
            return done(f"Errors found in the last 7 days: {n} across {len(wk)} analysed jumps.")
        return done(f"You have {len(hist)} analysed jumps in total, {len(wk)} in the last 7 days.")
    if re.search(r"\b(best|highest|max|longest|record)\b", q):
        hh = [r for r in hist if isinstance(r.get("height_m"), (int, float))]
        aa = [r for r in hist if isinstance(r.get("air_time_s"), (int, float))]
        if not hh and not aa:
            return done("No measured jumps yet — upload a jump video and your bests will appear in Progress.")
        lines = []
        if hh:
            b = max(hh, key=lambda r: r["height_m"])
            lines.append(f"Highest jump: {b['height_m'] * 100:.0f} cm ({_jump_line(b)}, {_when(b.get('ts'))}).")
        if aa:
            b = max(aa, key=lambda r: r["air_time_s"])
            lines.append(f"Longest air time: {b['air_time_s']:.2f} s ({_when(b.get('ts'))}).")
        return done("\n".join(lines))
    if re.search(r"\bcompare\b", q):
        jn = next((j for j in ("axel", "salchow", "toe loop", "loop", "flip", "lutz", "waltz") if j in q), None)
        pool = [r for r in hist if not jn or jn in str(r.get("jump") or r.get("name_display") or "").lower()]
        if len(pool) < 2:
            return done(f"There are fewer than two analysed {jn + ' ' if jn else ''}jumps to compare yet.")
        a, b = pool[0], pool[1]
        return done(f"Latest: {_jump_line(a)} ({_when(a.get('ts'))}).\nBefore: {_jump_line(b)} ({_when(b.get('ts'))}).")
    if re.search(r"\b(plan|session|training|workout|practice)\b", q) and re.search(r"\b(today|why|what)\b", q):
        t = s.get("today") or {}
        if not t.get("focus_label"):
            return done("There is no session for today yet: upload a jump video or pick a goal on the Training tab.")
        drills = [b.get("name") for b in (t.get("blocks") or []) if b.get("drill_id")]
        notes = [n for n in (t.get("notes") or []) if isinstance(n, str) and n.strip()]
        return done(
            f"Today's session focuses on {t['focus_label']}."
            + (f" Drills: {', '.join(drills)}." if drills else "")
            + ((" Why: " + " ".join(notes[:3])) if notes else "")
        )
    if re.search(r"\bcoach\b", q) and re.search(r"\b(said|say|comment|wrote|note|focus|told)\b", q):
        c = s.get("coach_comment")
        if not c:
            return done(
                "Your coach has not left a comment yet. You can share your code from Profile so they can follow your analyses."
            )
        return done(f"Your coach wrote: {c.get('text') if isinstance(c, dict) else c}")
    if re.search(r"\b(streak|in a row)\b", q):
        pg = s.get("progress") or {}
        return done(
            f"Your streak: {pg.get('streak_days') or 0} days in a row; {pg.get('sessions_7d') or 0} sessions in the last 7 days."
        )
    return None
