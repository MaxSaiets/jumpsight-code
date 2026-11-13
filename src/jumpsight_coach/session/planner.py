"""Multi-day plan: the day engine unfolded over a forecast with explicit rest days."""

from __future__ import annotations

import time

from .builder import build
from .focus import support_goals
from .outcomes import _SIM


def plan(profile, days: int = 14, lang: str = "en") -> dict:
    """A multi-day plan with the same adaptive engine as the day.

    The survey, physical tests, persistent gaps, history and 'worked / did not work' results all shape it, unlike a
    fixed template course.

    There is no real data about the future, so:
      day 1: built on what is known now;
      day 2+: a forecast under the explicit assumption 'everything works out', marked `provisional`, with a written reason.
    The forecast is rebuilt every time a real result appears: a single `fail` is enough for the following days to change.
    Presenting a forecast as a plan is the same as inventing a number, so it is marked.
    """
    # ── Rest days from the survey ────────────────────────────────────────────────
    # The training frequency from the survey decides the rest days: continuous load without recovery is a direct
    # path to overtraining, and no methodology prescribes it.
    _per_week = {0: 2, 1: 4, 2: 5, 3: 6}
    try:
        from ..skills import load as _sk

        _f = int((_sk().get("survey") or {}).get("freq", 1))
    except Exception:  # noqa: BLE001
        _f = 1
    _pw = _per_week.get(_f, 4)
    # evenly: we train on the days of the week that the frequency gives,
    _train = set()
    for w in range((days + 6) // 7):
        for k in range(_pw):
            _train.add(w * 7 + int(round(k * 7 / _pw)))

    out, sim = [], []
    prev = None
    _supports: list[str] = []
    forecast_token = _SIM.set(())
    try:
        for i in range(max(1, days)):
            if i not in _train:
                out.append(
                    {
                        "day_index": i + 1,
                        "rest": True,
                        "provisional": i > 0,
                        "focus": "rest",
                        "focus_text": ("rest — recovery is part of the plan, not a gap in it"),
                        "blocks": [],
                    }
                )
                continue
            _SIM.set(tuple(sim))
            # the main work on every second training day, and between them
            # the supporting target (support_goals); day 1 is always the main one.
            k = len([x for x in out if not x.get("rest")])
            sup = None
            if k % 2 == 1 and _supports:
                sup = _supports[(k // 2) % len(_supports)]
            d = build(profile, lang, support_goal=sup)
            if k == 0 and not _supports:
                _supports[:] = support_goals(d.get("focus", ""))
            d["day_index"] = i + 1
            d["provisional"] = i > 0
            if i > 0:
                d["provisional_because"] = (
                    "forecast: built assuming the earlier days went well. "
                    "It is rebuilt as soon as a real outcome arrives"
                )
            # whether the composition changed: it shows the engine responds rather than repeats
            ids = [b.get("drill_id") for b in d.get("blocks", []) if b.get("drill_id")]
            d["changed_from_previous"] = (ids != prev) if prev is not None else None
            prev = ids
            out.append(d)
            # we assume the day was done and everything worked out, and that is what drives
            # the mastery counter and pushes drills back by freshness.
            sim = sim + [
                {
                    "ts": time.time(),
                    "focus": d.get("focus", ""),
                    "simulated": True,
                    "blocks": [{"drill_id": x, "outcome": "ok"} for x in ids],
                }
            ]
    finally:
        _SIM.reset(forecast_token)
    _tr = [d for d in out if not d.get("rest")]
    uniq = len({tuple(b.get("drill_id") for b in d.get("blocks", [])) for d in _tr})
    return {
        "days": out,
        "n": len(out),
        "training_days": len(_tr),
        "rest_days": len(out) - len(_tr),
        "per_week": _pw,
        "distinct_days": uniq,
        "engine": "adaptive (same as /today)",
        "note": ("day 1 from what is known now; the rest is a forecast that is rebuilt after every session"),
    }
