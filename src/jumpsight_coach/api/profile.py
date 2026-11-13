"""Skater profile routes: survey, skill map and goal, working jump, fitness tests."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from jumpsight_core.paths import STATE_DIR

router = APIRouter()


@router.get("/survey")
def survey(lang: str = "en") -> list[dict]:
    from ..skills import SURVEY, load

    # Saved answers are returned, so the screen shows what was already answered instead of the defaults.
    saved = load().get("survey") or {}
    out = []
    for q in SURVEY:
        # value = the option index (a level score does not fit: for coach/age/pain all scores are 0)
        _cur = saved.get(q["id"])
        out.append(
            {
                "id": q["id"],
                "q": q["q"],
                "answered": _cur is not None,
                "value": int(_cur) if _cur is not None else None,
                "options": [{"label": o[0], "value": i, "score": o[1]} for i, o in enumerate(q["options"])],
            }
        )
    return out


class SurveyIn(BaseModel):
    answers: dict
    lang: str = "en"


@router.post("/survey")
def survey_save(inp: SurveyIn) -> dict:
    from ..skills import profile, save_survey

    save_survey(inp.answers)
    return profile(inp.lang)


@router.get("/skill_profile")
def skill_profile(lang: str = "en") -> dict:
    from ..skills import profile, skill_map

    out = profile(lang)
    # Skill map: per jump, the attempts, the clean ones, the spread of revolutions and the share of attempts
    # with each error. It answers "what the person cannot do yet", which the summary level does not.
    out["skill_map"] = skill_map(lang)
    return out


class SkillGoalIn(BaseModel):
    jump: str
    target_pct: float
    target_date: str
    lang: str = "en"


@router.get("/skill_goal")
def skill_goal_get(lang: str = "en") -> dict:
    from ..goal import with_progress

    return with_progress(lang) or {}


@router.post("/skill_goal")
def skill_goal_set(inp: SkillGoalIn) -> dict:
    from ..goal import save, with_progress

    save(inp.jump, inp.target_pct, inp.target_date)
    return with_progress(inp.lang) or {}


@router.delete("/skill_goal")
def skill_goal_clear() -> dict:
    from ..goal import clear

    clear()
    return {"ok": True}


# Working jump chosen in onboarding. Not a goal with a percentage and a deadline (skill_goal), just the
# working focus that the day plan and the name prior read.
_FOCUS_FILE = STATE_DIR / "focus_jump.json"


def _ff():
    from ..userctx import user_path

    return user_path(_FOCUS_FILE)


class FocusJumpIn(BaseModel):
    jump: str


@router.get("/focus_jump")
def focus_jump_get() -> dict:
    try:
        return json.loads(_ff().read_text(encoding="utf-8"))
    except Exception:
        return {"jump": None}


@router.post("/focus_jump")
def focus_jump_set(inp: FocusJumpIn) -> dict:
    import time as _t

    j = (inp.jump or "").strip()[:8]
    _ff().parent.mkdir(parents=True, exist_ok=True)
    _ff().write_text(json.dumps({"jump": j, "ts": _t.time()}), encoding="utf-8")
    return {"ok": True, "jump": j}


@router.get("/fitness/tests")
def fitness_tests(lang: str = "en") -> list[dict]:
    from ..fitness import TESTS

    return [
        {
            "id": t["id"],
            "group": t["group"],
            "name": t["name"],
            "how": t["how"],
            "unit": t["unit"],
            "target": t["target"],
            "source": t["source"],
        }
        for t in TESTS
    ]


@router.get("/fitness")
def fitness_get(lang: str = "en") -> dict:
    from ..fitness import FitnessStateUnavailable, gates, load
    from ..userctx import current_uid

    try:
        return {"profile": load(), "gates": gates(lang), "owner_uid": current_uid()}
    except FitnessStateUnavailable as error:
        raise HTTPException(
            503, "fitness profile unavailable", headers={"Retry-After": "30", "Cache-Control": "no-store"}
        ) from error


class FitnessIn(BaseModel):
    results: dict
    lang: str = "en"
    owner_uid: str | None = Field(default=None, max_length=40)


@router.post("/fitness")
def fitness_save(inp: FitnessIn) -> dict:
    from ..fitness import FitnessStateUnavailable, InvalidFitnessInput, gates, save
    from ..userctx import current_uid

    # The cookie decides the rights; the owner only rejects the draft of an old tab.
    if inp.owner_uid is not None and inp.owner_uid != current_uid():
        raise HTTPException(409, "fitness owner changed")
    try:
        d = save(inp.results)
        return {"profile": d, "gates": gates(inp.lang), "owner_uid": current_uid()}
    except InvalidFitnessInput as error:
        raise HTTPException(422, str(error)) from error
    except FitnessStateUnavailable as error:
        raise HTTPException(
            503, "fitness profile unavailable", headers={"Retry-After": "30", "Cache-Control": "no-store"}
        ) from error
