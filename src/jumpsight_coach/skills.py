"""Skill profile: survey plus assessment from video (not just words).

A skater's level is not guessed from a single jump (revolutions<1.5 -> beginner): on a poor video the revolutions
cannot be measured, and the system would see a master as a beginner.

The profile has two sources:
  1) SURVEY (self-report): how long they skate, which jumps they do
     consistently, whether there is a coach, training sessions per week, age group;
  2) ASSESSMENT FROM SEVERAL VIDEOS (measured): from the analysis history the best
     attempts are taken, giving the maximum measured revolution class, stability (share of
     clean ones), typical errors, height/flight time.
Final level = min(declared, measured+1). Self-report cannot raise the level more than
one step above what is measured (protection against inflation); measured data without a
self-report works on its own.
"""

from __future__ import annotations

import json
import time

from jumpsight_core.paths import STATE_DIR

PROFILE = STATE_DIR / "skill_profile.json"


def _pp():
    from .userctx import user_path

    return user_path(PROFILE)


# survey questions (id, text, options -> level points)
SURVEY = [
    {
        "id": "years",
        "q": "How long have you been skating?",
        "options": [("<1 year", 1), ("1-3 years", 2), ("3-6 years", 3), ("6+ years", 4)],
    },
    {
        "id": "jumps",
        "q": "Which jumps do you land CONSISTENTLY?",
        "options": [("still learning first ones", 1), ("singles", 2), ("doubles", 3), ("double axel / triples", 4)],
    },
    {"id": "freq", "q": "Sessions per week?", "options": [("1-2", 1), ("3-4", 2), ("5-6", 3), ("daily, 2+/day", 4)]},
    {"id": "coach", "q": "Do you have a coach?", "options": [("no", 0), ("sometimes", 0), ("yes, regularly", 0)]},
    {
        "id": "age",
        "q": "Age group",
        # '12 or under' and '13-17' leave no age outside the groups
        "options": [("12 or under", 0), ("13-17", 0), ("adult", 0)],
    },
    # Physical abilities cannot be measured from a jump video, so they are asked directly, and the answer is
    # used as a gate, not as a level score.
    {
        "id": "balance",
        "q": "How long can you hold a one-foot balance?",
        "options": [("under 5 s", 1), ("5-15 s", 2), ("over 15 s", 3)],
    },
    {
        "id": "pain",
        "q": "Any pain or injury right now?",
        "options": [("none", 0), ("some discomfort", 0), ("yes, it hurts", 0)],
    },
]

LEVEL_NAMES = {1: "Beginner", 2: "Intermediate", 3: "Advanced", 4: "Competitive"}
SURVEY_BY_ID = {q["id"]: q for q in SURVEY}


def load() -> dict:
    if _pp().exists():
        return json.loads(_pp().read_text(encoding="utf-8"))
    return {}


def save_survey(answers: dict) -> dict:
    """answers: {question_id: INDEX of the chosen option}.

    The option index is stored and the level score is taken from the table: the coach, age and pain questions all
    have scores of 0, so storing a score would leave the pain gate and the growth-spurt branch dead and tell
    everyone 'you train without a coach'.
    """
    idx = {}
    for q in SURVEY:
        v = answers.get(q["id"])
        try:
            idx[q["id"]] = max(0, min(len(q["options"]) - 1, int(v)))
        except (TypeError, ValueError):
            continue
    pts = [SURVEY_BY_ID[k]["options"][i][1] for k, i in idx.items() if k in ("years", "jumps", "freq")]
    claimed = max(1, round(sum(pts) / len(pts))) if pts else 1
    answers = idx
    from .statefile import update_json

    def _mut(cur):
        prof = dict(cur or {})
        prof.update({"survey": answers, "claimed_level": claimed, "survey_ts": time.time()})
        return prof

    return update_json(_pp(), _mut, {})


def assess_from_history(min_videos: int = 2) -> dict:
    """Assessment from video: level from the really measured attempts of the history.

    Only reliable attempts go into the count: three unreliable clips would make a beginner 'Competitive'.
    """
    from math import isfinite
    from statistics import median

    from .jobs import execution_clean_state, history, rev_is_usable

    hist = [
        h
        for h in history()
        if isinstance(h.get("revolutions"), (int, float))
        and not isinstance(h.get("revolutions"), bool)
        and isfinite(h["revolutions"])
        and h["revolutions"] >= 0
        and rev_is_usable(h)
        and h.get("count_supported", True)
        and h.get("confidence") != "low"
    ]
    if len(hist) < min_videos:
        return {"measured_level": None, "n_videos": len(hist), "need_more": min_videos - len(hist)}
    revs = sorted((h["revolutions"] for h in hist), reverse=True)
    best = revs[0]
    # A typical measured attempt, not the three best. This is not evidence of stability.
    consistent = median(revs)
    execution = [state for h in hist if (state := execution_clean_state(h)) is not None]
    clean_pct = round(100 * sum(execution) / len(execution)) if execution else None
    lvl = 1
    if consistent >= 2.4:
        lvl = 4
    elif consistent >= 1.8:
        lvl = 3
    elif consistent >= 1.3:
        lvl = 2
    errs = {}
    for h in hist:
        for e in h.get("errors", []):
            errs[e] = errs.get(e, 0) + 1
    weak = sorted(errs, key=errs.get, reverse=True)[:2]
    return {
        "measured_level": lvl,
        "n_videos": len(hist),
        "best_revolutions": round(best, 2),
        "consistent_revolutions": round(consistent, 2),
        "assessment_method": "history_median",
        "clean_pct": clean_pct,
        "clean_assessed_total": len(execution),
        "weak_points": weak,
    }


MIN_ATTEMPTS = 3  # fewer: no verdict, we say 'too few attempts'
OWNED = 0.20  # error in no more than 20% of attempts: the skill is owned
NOT_OWNED = 0.60  # error in 60% or more of attempts: the skill is not there yet


def skill_map(lang: str = "en") -> dict:
    """What the person cannot do yet, from a series of attempts, not from one.

    Separate from assess_from_history(): that one computes one level over the whole history and returns the 'weak
    spots' as just the most frequent error codes, which is not enough for assignment:

      • a fall in 1 attempt out of 20 and a fall in 8 of 10 are different diagnoses, but in a frequency count both look like 'fall: N times';
      • a person may have a Salchow and not a Lutz, and a level summarized over all jumps hides that difference;
      • 'stable' must not be the average of the three best attempts: 1.9/1.9/1.9 and 2.4/1.8/1.5 give almost the same
        number, although the second is the sign that the jump is not yet owned.

    For each jump the share of attempts with each error is counted among the assessed checks of its code, with the
    spread of revolutions. A verdict on an error is given only from MIN_ATTEMPTS assessed checks; the number of
    videos alone does not prove that this sample is sufficient.
    """
    from .jobs import error_check_state, execution_clean_state, history, jump_is_resolved

    by_jump: dict[str, list] = {}
    for h in history():
        j = h.get("jump") or "?"
        if j in ("not resolved", "?"):
            continue
        # a name the system did not determine must not become a row of the skills profile, otherwise a 'Salchow'
        # in the profile would come from a guess, not from a measurement. The journal writes this flag
        # (jobs.add_history_jumpsight).
        if not jump_is_resolved(h):
            continue
        by_jump.setdefault(j, []).append(h)

    out = []
    for jump, rows in sorted(by_jump.items(), key=lambda kv: -len(kv[1])):
        n = len(rows)
        # Only measured numbers: 'best' and 'median' on the profile screen must not include records whose
        # uncertainty band forbids counting the number as a measurement. One rule for the whole project:
        # jobs.rev_is_usable, which also handles records without the flag.
        from .jobs import rev_is_usable

        revs = sorted(r["revolutions"] for r in rows if r.get("revolutions") is not None and rev_is_usable(r))
        spread = round(revs[-1] - revs[0], 2) if len(revs) >= 2 else None
        execution = [state for r in rows if (state := execution_clean_state(r)) is not None]
        clean_n = sum(execution)
        err_n: dict[str, int] = {}
        for r in rows:
            for e in set(r.get("errors") or []):
                if error_check_state(r, e) is True:
                    err_n[e] = err_n.get(e, 0) + 1
        gaps = []
        for code, k in sorted(err_n.items(), key=lambda kv: -kv[1]):
            assessed = sum(error_check_state(r, code) is not None for r in rows)
            rate = k / assessed
            if assessed < MIN_ATTEMPTS:
                verdict = "too_few"
            elif rate >= NOT_OWNED:
                verdict = "not_owned"
            elif rate > OWNED:
                verdict = "unstable"
            else:
                verdict = "occasional"
            gaps.append({"code": code, "in_attempts": k, "of": assessed, "rate": round(rate, 2), "verdict": verdict})
        out.append(
            {
                "jump": jump,
                "attempts": n,
                "clean": clean_n,
                "clean_pct": round(100 * clean_n / len(execution)) if execution else None,
                "clean_assessed_total": len(execution),
                "revolutions_median": revs[len(revs) // 2] if revs else None,
                "revolutions_best": revs[-1] if revs else None,
                "revolutions_spread": spread,
                "gaps": gaps,
                "enough_data": n >= MIN_ATTEMPTS,
                "note": (
                    f"only {n} attempt(s) — not enough to tell a one-off from a real gap" if n < MIN_ATTEMPTS else ""
                ),
            }
        )
    return {
        "jumps": out,
        "min_attempts": MIN_ATTEMPTS,
        "thresholds": {"owned_at_or_below": OWNED, "not_owned_at_or_above": NOT_OWNED},
    }


def persistent_gaps(min_attempts: int = MIN_ATTEMPTS) -> list[str]:
    """Error codes in 60%+ of assessed checks of AT LEAST one jump.

    This is 'cannot do yet', as opposed to 'did not work this time'. The session sets the focus here, not on a random
    error of the last clip.
    """
    out: list[str] = []
    for j in skill_map().get("jumps", []):
        if j["attempts"] < min_attempts:
            continue
        for g in j["gaps"]:
            if g["of"] >= min_attempts and g["verdict"] == "not_owned" and g["code"] not in out:
                out.append(g["code"])
    return out


def profile(lang: str = "en") -> dict:
    """Summary profile: declared + measured + final level."""
    prof = load()
    claimed = prof.get("claimed_level")
    meas = assess_from_history()
    m = meas.get("measured_level")
    if m and claimed:
        final = min(claimed, m + 1)  # declaration not higher than measured+1
        basis = "measured + survey"
    elif m:
        final, basis = m, ("measured")
    elif claimed:
        final = claimed
        basis = "self-reported, not yet confirmed by video"
    else:
        final, basis = None, ("no data")
    name = LEVEL_NAMES.get(final) if final else None
    out = {"level": final, "level_name": name, "basis": basis, "claimed_level": claimed, **meas}
    if m and claimed and claimed > m + 1:
        out["note"] = "self-reported level exceeds measured — upload a few more videos of your best jumps"
    if meas.get("need_more"):
        # The full count, not only the usable ones: n_videos counts only the records that suit level assessment
        # (have revolutions, the clip holds them, confidence not low), but on screen a person who uploaded two
        # videos and saw '1 video' reads it as 'upload did not work'. Both numbers and the reason for the gap
        # are visible.
        from .jobs import history as _vh

        _all = len(_vh())
        _fit = int(meas.get("n_videos") or 0)
        _skipped = max(0, _all - _fit)
        out["n_videos_total"] = _all
        out["n_videos_usable"] = _fit
        _en = f"upload {meas['need_more']} more videos so the system can measure your level"
        if _skipped:
            _en = (
                f"videos in your profile: {_all}, usable for the level "
                f"assessment: {_fit}. The other {_skipped} do not count — "
                f"revolutions were not measured there, or the confidence "
                f"was too low. " + _en
            )
        if _fit == 0 and _all >= 3:
            # After several videos with no usable one, «upload 2 more» is not helpful: say what limits the
            # measurement, not just «more». These are limits of measurement, not an order (PRODUCT.md #4): the
            # person sees under which conditions the revolutions are measured, and decides for themselves
            _en = (
                f"Rotations were not measured in any of your {_all} videos — "
                f"and the level is computed from them alone. Rotations are "
                f"measured when the whole jump is in frame, the camera is still and the video is 60 fps."
            )
        out["note"] = _en
    return out
