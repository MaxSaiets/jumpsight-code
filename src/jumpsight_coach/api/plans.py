"""Day session and multi-day plan routes: /today, /plan, goals, readiness, completion."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jumpsight_core.paths import OUTPUT_DIR

from ..core import load_kb

router = APIRouter()


@router.get("/today")
def today(lang: str = "en", goal: str = "", feel: str = "", want: str = "") -> dict:
    """Session for today: one day, step by step, taking past sessions into account.

    `goal` is an optional input without video ("I want rotation", "I want flexibility"). A session by goal is
    built from the same base and the same rules; only the source of the goal differs, and the output says so.
    """
    from ..core import load_profile
    from ..jobs import history as vhist
    from ..session import build, build_for_goal

    if goal:
        return build_for_goal(goal, lang, feel, want)
    h = vhist()
    if not h:
        return {"empty": True, "message": "Today's session is built from your jump video."}
    # Not h[0] blindly: records written by the default engine have no out/{stem}_result.json file, which is
    # needed here. The newest record for which the file really exists is used.
    f = None
    match_rec = None
    for rec in h:
        cand = OUTPUT_DIR / f"{rec['stem']}_result.json"
        if cand.exists():
            f = cand
            match_rec = rec
            break
    if f is None:
        return {"empty": True, "message": "no analysis result"}
    return build(load_profile(f), lang, feel, want, analysis_ts=match_rec.get("ts"))


@router.get("/plan")
def plan(lang: str = "en", days: int = 14) -> dict:
    """A multi-day plan by the same engine as /today.

    Each day goes through the same rules: level, survey, physical tests, persistent gaps, drill freshness and
    the mastery counter. Days after the nearest one are marked `provisional`: they are a forecast, not a
    promise.
    """
    from ..core import load_profile
    from ..jobs import history as vhist
    from ..session import plan as build_plan

    h = vhist()
    if not h:
        return {"empty": True, "message": "Upload a jump video — the plan is built from it"}
    # the same guard as /today: the newest record that has a result file
    f = None
    for rec in h:
        cand = OUTPUT_DIR / f"{rec['stem']}_result.json"
        if cand.exists():
            f = cand
            break
    if f is None:
        return {"empty": True, "message": "no analysis result"}
    return build_plan(load_profile(f), max(1, min(days, 28)), lang)


@router.get("/goals")
def goals(lang: str = "en") -> list[dict]:
    """Goals the person can choose themselves, without video.

    Only goals for which the base really has drills: the list is built from the base's own targets, so it
    cannot diverge from the content.
    """
    from ..session import GOAL_LABELS

    drills, _ = load_kb()
    cnt: dict[str, int] = {}
    for d in drills:
        if d.get("kind") == "do_not_recommend":
            continue
        for t in d.get("targets") or []:
            cnt[t] = cnt.get(t, 0) + 1
    return [
        {"code": c, "label": GOAL_LABELS.get(c, c), "drills": n}
        for c, n in sorted(cnt.items(), key=lambda kv: -kv[1])
        if n >= 2
    ]


class DoneIn(BaseModel):
    done: list[str] = []
    focus: str = ""
    note: str = ""
    outcomes: dict[str, str] = {}  # drill_id -> ok | partial | fail
    effort: str = ""  # easy | right | much
    session_id: str = ""  # stable id for a repeated POST


@router.get("/readiness")
def readiness(lang: str = "en") -> dict:
    """What the system knows about the person before it advises anything.

    The state of knowledge is explicit: what has been measured, what is missing, and what exactly that makes
    coarser.
    """
    from ..fitness import gates
    from ..fitness import load as fit_load
    from ..jobs import history as vhist
    from ..skills import load as sk_load
    from ..skills import profile as sk_profile

    sk = sk_load()
    prof = sk_profile(lang)
    fit = fit_load()
    hist = vhist()

    items = [
        {
            "key": "survey",
            "done": bool(sk.get("survey")),
            "title": "Experience survey",
            "gives": "level, sessions per week, coach, age group, pain",
            "missing_costs": ("without it the level defaults to the lowest and spotter-only drills stay hidden"),
        },
        {
            "key": "fitness",
            "done": bool(fit.get("results") or fit.get("groups")),
            "title": "Fitness tests",
            "gives": ("leg power, flexibility, endurance, balance — none of which a jump video shows"),
            "missing_costs": "volume and explosive work are not adjusted",
        },
        {
            "key": "videos",
            "done": len(hist) >= 2,
            "count": len(hist),
            "title": "Jump videos",
            "gives": "measured level and the actual errors",
            "missing_costs": ("one clip is not enough — a single jump does not support a level estimate"),
        },
    ]
    ready = sum(1 for i in items if i["done"])
    return {
        "items": items,
        "ready": ready,
        "total": len(items),
        "level": prof.get("level"),
        "level_name": prof.get("level_name"),
        "basis": prof.get("basis"),
        "gates": gates(lang),
        "can_plan": len(hist) >= 1,
        "plan_note": ("A session can be built now, but the more of this is measured, the better it fits you."),
    }


@router.post("/today/complete")
def today_complete(inp: DoneIn) -> dict:
    from ..session import complete

    try:
        return complete(inp.done, inp.focus, inp.note, inp.outcomes, inp.effort, inp.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/sessions")
def sessions() -> list[dict]:
    from ..session import history

    return history()
