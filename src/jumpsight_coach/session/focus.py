"""Focus selection: goal mapping, evidence guard for the day's focus, stuck errors, support goals."""

from __future__ import annotations

from ..core import CODE_ALIASES, load_kb
from .rules import prescription


def _goal_of(code: str) -> str:
    """Analyzer error code -> target of the drill base (the same dictionary as in core.Profile.goals()).

    Measured on 12 analyses of one user: jumpsight assigned touch_down in 8 of 12, yet "stable landing" matched 0 of them,
    because goals() is already translated by the dictionary (touch_down -> landing_stability) while the counters
    compared the target with raw journal codes. Four of the seven codes of the typical engine (step_out, touch_down,
    hand_down, tilted_axis) could then never become the focus. Every comparison therefore goes through this function.
    """
    return CODE_ALIASES.get(code, code)


def _goals_of(codes) -> set[str]:
    return {_goal_of(c) for c in (codes or [])}


def _pick_focus(goals: list[str], persistent: list[str] | None = None) -> str:
    """The most important of the measured errors, not just the first one.

    persistent: errors that persist in 60%+ of attempts (skills.skill_map). This is "cannot do yet", as opposed to "did not work this time". A fall in 1 attempt out of 20 must not weigh the same as a fall in 8 of 10, so at equal priority a stable gap comes first, and among gaps the safety order from prescription.yaml stays the main criterion.
    """
    order = {r["code"]: r.get("rank", 99) for r in (prescription().get("priority") or [])}
    pers = _goals_of(persistent)
    cand = list(dict.fromkeys(list(goals) + sorted(pers)))
    if not cand:
        return "basics_rotation"
    return sorted(cand, key=lambda g: (order.get(g, 50), 0 if g in pers else 1))[0]


# The same threshold, 'too few attempts, no verdict', as in skills.py: two different numbers under the
# same meaning would diverge at the first edit.
try:
    from ..skills import MIN_ATTEMPTS as _SKILL_MIN_ATTEMPTS
except Exception:  # noqa: BLE001
    _SKILL_MIN_ATTEMPTS = 3

# 'Not from one video' means literally two different analyses: one analysis is exactly the case that
# names a false source.
MIN_ANALYSES_FOR_FOCUS = 2


def _measured_attempts() -> int:
    """How many REAL measurements are in the journal (not traces of failed attempts)."""
    try:
        from ..jobs import history

        return sum(1 for h in history() if h.get("outcome") != "not_measured" and h.get("revolutions") is not None)
    except Exception:  # noqa: BLE001
        return 0


def _analyses_with_code(code: str, records=None, *, confident=True) -> int:
    """Number of known video sources with the corresponding error.

    Several attempts of one file give one source; an unknown origin does not prove a separate video.
    """
    try:
        from ..jobs import history, video_source_key

        records = history() if records is None else records
        sources = {
            source
            for h in records
            if h.get("outcome") != "not_measured"
            and code in _goals_of(_confident_errors(h) if confident else h.get("errors"))
            and (source := video_source_key(h)) is not None
        }
        return len(sources)
    except Exception as exc:  # noqa: BLE001
        import sys

        print(f"[coach-focus] evidence unavailable: {exc}", file=sys.stderr)
        return 0


def _confident_errors(rec: dict) -> list[str]:
    """Only explicit medium/high errors confirm the auto focus.

    A record without a tier stays in skills; unknown confidence is not medium. The frequency of low signals does not raise their confidence.
    """
    conf = rec.get("errors_conf")
    codes = rec.get("errors") or []
    if not isinstance(conf, dict):
        return []
    return [c for c in codes if str(conf.get(c) or "").lower() in ("medium", "high")]


def _error_confidence(profile, goal: str) -> str | None:
    """Detector confidence in the error of the LAST analysis that leads to this target."""
    best = None
    rank = {"low": 0, "medium": 1, "high": 2}
    for e in getattr(profile, "errors_found", None) or []:
        if _goal_of(str(e.get("code") or "")) != goal:
            continue
        c = str(e.get("confidence") or "").lower() or None
        if c not in rank:
            continue
        if best is None or rank.get(c, 0) > rank.get(best, 0):
            best = c
    return best


def guard_focus(focus: str, persistent: list[str] | None, profile) -> tuple[str, dict | None]:
    """The focus has medium/high evidence from two known video files.

    A persistent frequency does not bypass the source/confidence guard. A repeat of low detector output remains a signal, not a confirmed skill.
    """
    pers = _goals_of(persistent)
    conf = _error_confidence(profile, focus)
    try:
        from ..jobs import history

        records = history()
    except Exception as exc:  # noqa: BLE001
        import sys

        print(f"[coach-focus] history unavailable: {exc}", file=sys.stderr)
        records = []
    seen_in = _analyses_with_code(focus, records)
    if seen_in >= MIN_ANALYSES_FOR_FOCUS and (focus in pers or conf in ("medium", "high")):
        return focus, None
    seen_any = _analyses_with_code(focus, records, confident=False)
    return "basics_rotation", {
        "kind": "unsupported_single_analysis",
        "rejected_code": focus,
        "analyses_with_code": seen_in,
        "analyses_with_code_any": seen_any,
        "min_analyses": MIN_ANALYSES_FOR_FOCUS,
        "evidence_unit": "video_source",
        "measured_attempts": _measured_attempts(),
        # the field name is kept because the UI reads it; the value is the error's confidence
        "rotation_confidence": conf or "unknown",
    }


def stuck_errors(min_runs: int = 4) -> list[str]:
    """Errors that persist across min_runs analyses IN A ROW.

    The main signal for a person is not 'what now' but 'what has not moved in a month of work'. Transfer of off-ice
    drills to the ice is not automatic (Bruening & Richards 2006), so when an error stays in place, the honest answer
    is not another drill but 'needs a coach's eye'.
    """
    from ..jobs import history

    h = history()
    if len(h) < min_runs:
        return []
    runs = [_goals_of(x.get("errors")) for x in h[:min_runs]]
    common = set.intersection(*runs) if runs else set()
    return sorted(common)


# Anchor goals for the 14-day forecast. A coach alternates the main work with supporting work, the work that
# removes the cause of the main one (measured: two alternating templates gave 3 different days out of 8 with
# one focus for two weeks). The link from the knowledge base (causes.yaml -> fix_targets) is used first; where
# there is none, this is the map of foundations. A coaching heuristic, evidence level B, not a measurement.
_SUPPORT_FALLBACK = {
    "basics_rotation": ["landing_stability", "air_position"],
    "air_position": ["basics_rotation", "axis_tilt"],
    "axis_tilt": ["air_position", "landing_stability"],
    "late_check_out": ["landing_stability", "air_position"],
    "landing_stability": ["stiff_landing_knee", "late_check_out"],
    "spin_flexibility": ["spin_position", "balance_control"],
    "spin_position": ["spin_flexibility", "balance_control"],
    "balance_control": ["landing_stability", "spin_position"],
}


def support_goals(focus: str) -> list[str]:
    """Anchor goals for the main focus: first from the knowledge base, then foundations."""
    try:
        _, causes = load_kb()
    except Exception:  # noqa: BLE001
        causes = {}
    out: list[str] = []
    for c in (causes.get(focus) or {}).get("causes") or []:
        for ft in c.get("fix_targets") or []:
            if ft != focus and ft not in out:
                out.append(ft)
    for ft in _SUPPORT_FALLBACK.get(focus, []):
        if ft != focus and ft not in out:
            out.append(ft)
    return out[:3]
