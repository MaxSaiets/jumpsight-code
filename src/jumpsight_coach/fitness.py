"""Physical tests: leg strength, flexibility, endurance, balance.

Why a separate screen. These qualities are NOT measured from a jump video: there one sees only what happened in the flight. A session without them is incomplete: an explosive drill is pointless if the legs are weak; Biellmann is impossible without flexibility; the volume has to be cut if there is no endurance.

The principle is the same as in the whole system: we do not invent, we MEASURE. Here the measuring tool is standard field tests, which the person does alone in 10 minutes, with norms from the literature.

The tests were chosen by three criteria: (1) they can be done at home without equipment, (2) they have published norms, (3) they relate directly to the jump.
"""

from __future__ import annotations

import json
import math
import time

from jumpsight_core.paths import STATE_DIR

PROFILE = STATE_DIR / "fitness.json"


class InvalidFitnessInput(ValueError):
    """Rejects the whole payload before any reading or writing of the profile."""


class FitnessStateUnavailable(RuntimeError):
    """The existing profile cannot be read or safely updated."""


def _validate_results(results: dict) -> None:
    if not isinstance(results, dict):
        raise InvalidFitnessInput("fitness results must be an object")
    known_ids = {test["id"] for test in TESTS}
    for key, value in results.items():
        if key not in known_ids:
            raise InvalidFitnessInput("unknown fitness test")
        if value is None or value == "":
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise InvalidFitnessInput("fitness results must be finite numbers")
        try:
            valid = math.isfinite(float(value))
        except (ValueError, OverflowError):
            valid = False
        if not valid:
            raise InvalidFitnessInput("fitness results must be finite numbers")


def _validate_profile(data: dict) -> None:
    if not isinstance(data, dict):
        raise FitnessStateUnavailable("invalid fitness profile structure")
    try:
        _validate_results(data.get("raw", {}))
    except InvalidFitnessInput as error:
        raise FitnessStateUnavailable("invalid stored fitness results") from error
    groups = data.get("groups", {})
    if not isinstance(groups, dict):
        raise FitnessStateUnavailable("invalid fitness groups")
    for group in groups.values():
        score = group.get("score") if isinstance(group, dict) else None
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not 0 <= score <= 2
            or not math.isfinite(score)
            or ("grade" in group and group["grade"] not in ["A", "B", "C"])
        ):
            raise FitnessStateUnavailable("invalid fitness group score")


def _pp():
    from .userctx import user_path

    return user_path(PROFILE)


# Norms: standing broad jump and CMJ, classic field tests of leg strength
# (NSCA); sit-and-reach: flexibility of the back of the body; plank and
# squats: local endurance. Thresholds are given as fractions of
# height/age, so that no equipment is required.
TESTS = [
    {
        "id": "broad_jump",
        "group": "leg strength",
        "name": "Standing broad jump",
        "how": [
            "stand, feet shoulder-width apart",
            "squat, swing arms and jump forward as far as possible",
            "measure from the starting line to the heel",
        ],
        "unit": "% of your height",
        "input": "number",
        "bands": [
            (0, 80, "below the norm — leg strength limits jump height"),
            (80, 110, "average — there is room for growth"),
            (110, 999, "good — leg strength is not a limiter"),
        ],
        "target": "skaters: 100-130% of height",
        "source": "NSCA field tests; Podolsky 1990 (leg strength ↔ jump height)",
    },
    {
        "id": "cmj_reach",
        "group": "leg strength",
        "name": "Countermovement jump (reach)",
        "how": [
            "stand sideways to the wall, extend your arm — mark the height",
            "squat and jump, touch the wall as high as possible",
            "the difference between marks — your result in cm",
        ],
        "unit": "cm",
        "input": "number",
        "bands": [
            (0, 25, "low explosive strength — prioritize plyometrics"),
            (25, 40, "average"),
            (40, 999, "high explosive strength"),
        ],
        "target": "junior skaters 25-45 cm",
        "source": "Hunnicutt 2016 (plyometrics in figure skating, p<0.001)",
    },
    {
        "id": "sit_reach",
        "group": "flexibility",
        "name": "Sit and reach",
        "how": [
            "sit, legs straight together, feet to the wall",
            "reach forward with your hands on the floor, without jerks",
            "measure how far the fingers reach relative to the toes (± cm)",
        ],
        "unit": "cm from feet",
        "input": "number",
        "bands": [
            (-99, 0, "limited flexibility — spiral positions premature"),
            (0, 10, "sufficient for basic positions"),
            (10, 99, "good — can work on Bilman"),
        ],
        "target": "for spirals and libelles need 0 and above",
        "source": "ACSM field tests",
    },
    {
        "id": "split_gap",
        "group": "flexibility",
        "name": "Straddle split gap",
        "how": ["sit in a split as far as you can, without pain", "measure the distance from the pelvis to the floor"],
        "unit": "cm to floor",
        "input": "number",
        # lower = better, so the bands run from WORST to best: score=i is computed from the band index (a reversed
        # order would drop a full split to "weak" flexibility)
        "bands": [
            (20, 999, "flexibility severely limits elements"),
            (5, 20, "work on flexibility is needed"),
            (0, 5, "split is present or almost present"),
        ],
        "target": "for spirals and Bilman — 0-5 cm",
        "source": "coaching practice (Bilman ladder)",
    },
    {
        "id": "plank",
        "group": "endurance",
        "name": "Front plank hold",
        "how": [
            "support on forearms, body in a straight line",
            "hold until the hips start to sag",
            "record time in seconds",
        ],
        "unit": "seconds",
        "input": "number",
        "bands": [(0, 45, "weak core — axis in flight will wobble"), (45, 90, "sufficient"), (90, 999, "strong core")],
        "target": "60+ seconds",
        "source": "ACSM core endurance norms",
    },
    {
        "id": "squats_60s",
        "group": "endurance",
        "name": "Squats in 60 s",
        "how": ["squat to a 90° knee angle, back straight", "count clean repetitions per minute"],
        "unit": "reps",
        "input": "number",
        "bands": [(0, 25, "low leg endurance — keep volume small"), (25, 40, "average"), (40, 999, "good")],
        "target": "30-45 repetitions",
        "source": "field: local muscular endurance",
    },
    {
        "id": "balance_s",
        "group": "balance",
        "name": "One-foot balance",
        "how": [
            "stand on the landing foot, free leg behind",
            "hold the exit position, arms to the sides",
            "stopwatch until loss of balance",
        ],
        "unit": "seconds",
        "input": "number",
        "bands": [
            (0, 10, "short balance — simplify single-leg exercises"),
            (10, 30, "sufficient for basic landings"),
            (30, 999, "stable balance"),
        ],
        "target": "20+ seconds",
        "source": "adultsskatetoo: 5+ as a prerequisite for waltz",
    },
]


def _band(test: dict, value: float) -> str:
    for lo, hi, txt in test["bands"]:
        if lo <= value < hi:
            return txt
    return ""


def load() -> dict:
    path = _pp()
    try:
        if not path.exists():
            return {}
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FitnessStateUnavailable("fitness profile unreadable") from error
    _validate_profile(d)
    # A default score of 0 for an unmatched raw value is not evidence of weakness, so only the read projection is
    # updated; the file and the measurement time are not changed.
    raw = d.get("raw", {})
    if any(raw.get(t["id"]) not in (None, "") and not _band(t, float(raw[t["id"]])) for t in TESTS):
        derived = _build(raw)
        d.update({key: derived[key] for key in ("bands", "groups", "assessments")})
    # profiles without a grade field get one derived from the score, otherwise they would show as red
    for g in (d.get("groups") or {}).values():
        if isinstance(g, dict) and "grade" not in g:
            s = g.get("score", 0)
            g["grade"] = "C" if s < 0.7 else "B" if s < 1.5 else "A"
    return d


def save(results: dict) -> dict:
    """results: {test_id: number}. Computes the score by groups.

    Saving a single result (cmj_reach) must not wipe the other six."""
    # Merge under the lock: reading, merging and writing as three separate steps would let two simultaneous saves
    # erase each other's tests. The value is taken inside update_json.
    # First check the WHOLE payload: an invalid field must not commit a valid field.
    _validate_results(results)

    from .statefile import update_json

    _box: dict = {}
    path = _pp()

    def _mut(cur):
        # The check runs under the same lock, before merge/write; a default does not erase the file.
        if cur is None and path.exists():
            raise FitnessStateUnavailable("fitness profile unreadable")
        prev = {} if cur is None else cur
        _validate_profile(prev)
        merged_raw = dict(prev.get("raw") or {})
        merged_raw.update({k: v for k, v in results.items() if v not in (None, "")})
        _box["data"] = _build(merged_raw)
        return _box["data"]

    return update_json(path, _mut, None)


def _build(merged_raw: dict) -> dict:
    data = {"ts": time.time(), "raw": merged_raw, "bands": {}, "groups": {}, "assessments": {}}
    by_group: dict[str, list[int]] = {}
    for t in TESTS:
        v = merged_raw.get(t["id"])
        if v in (None, ""):
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        band = _band(t, v)
        if not band:
            data["bands"][t["id"]] = "Unrated: result is outside the available reference bands."
            data["assessments"][t["id"]] = {"status": "unrated", "reason": "outside_reference"}
            continue
        data["bands"][t["id"]] = band
        # 0 = weak, 1 = medium, 2 = good
        score = 0
        for i, (lo, hi, _x) in enumerate(t["bands"]):
            if lo <= v < hi:
                score = i
        by_group.setdefault(t["group"], []).append(score)
    for g, scores in by_group.items():
        avg = sum(scores) / len(scores)
        # grade is a machine tag, NOT text. The interface colored the badge
        # by comparing label==='good', and after translation into English
        # every group would turn red: the color depended on the language.
        data["groups"][g] = {
            "score": round(avg, 2),
            "grade": ("C" if avg < 0.7 else "B" if avg < 1.5 else "A"),
            "label": ("weak" if avg < 0.7 else "average" if avg < 1.5 else "good"),
        }
    return data


def gates(lang: str = "en") -> dict:
    """What physical tests CHANGE in a session. Only what is measured, no guesses."""
    d = load()
    g = d.get("groups") or {}
    raw = d.get("raw") or {}
    # GROUP KEYS are English and STABLE: they become keys of the groups
    # dictionary and must not depend on display text (localize translates values, not keys).
    out = {
        "notes": [],
        "limit_power": False,
        "limit_volume": False,
        "limit_flex": False,
        "limit_balance": False,
        "has_data": bool(g),
        "measured_groups": sorted(g),
    }
    if not g:
        return out
    if (g.get("leg strength") or {}).get("score", 2) < 0.7:
        out["limit_power"] = True
        out["notes"].append("leg strength is low — explosive work in small volume, base strength first")
    if (g.get("endurance") or {}).get("score", 2) < 0.7:
        out["limit_volume"] = True
        out["notes"].append("endurance is low — shorter session, more rest between sets")
    if (g.get("flexibility") or {}).get("score", 2) < 0.7:
        out["limit_flex"] = True
        out["notes"].append("flexibility is the limiter — spiral positions and Biellmann are not given yet")
    try:
        balance_value = float(raw.get("balance_s", 99))
        balance_test = next(t for t in TESTS if t["id"] == "balance_s")
        if _band(balance_test, balance_value) and balance_value < 10:
            out["limit_balance"] = True
            out["notes"].append("one-foot balance under 10 s — single-support drills are simplified")
    except (TypeError, ValueError):
        pass
    return out
