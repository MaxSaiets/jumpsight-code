"""Prescription rules from kb/prescription.yaml, science gates and goal labels."""

from __future__ import annotations

import yaml

from jumpsight_core.paths import KB_DIR

_PRESC: dict | None = None


def prescription() -> dict:
    """Assignment rules from kb/prescription.yaml (order, volume, history)."""
    global _PRESC
    if _PRESC is None:
        p = KB_DIR / "prescription.yaml"
        _PRESC = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _PRESC


def science_for(goals: list[str], fit: dict | None = None) -> list[dict]:
    """Level-A 'when -> what' rules that WORKED on this profile.

    The science becomes visible next to the session: the person sees not only what to do but on what basis, and can
    check the source.
    The gates are not decorative: the rule about explosive work deliberately does not fire when the test showed weak
    leg strength, since plyometrics rely on base strength.
    """
    fit = fit or {}
    g = set(goals or [])
    out = []
    for r in prescription().get("science_gates") or []:
        w = r.get("when", "")
        hit = False
        if "low height" in w:
            hit = bool(g & {"low_height", "rotation_power"}) and not fit.get("limit_power")
        elif "straight knee" in w:
            hit = bool(g & {"stiff_landing_knee", "fall", "landing_stability"})
        elif "off-ice" in w:
            hit = True  # applies to every session
        if hit:
            out.append(
                {
                    "when": r.get("when"),
                    "then": r.get("then"),
                    "why": r.get("why"),
                    "evidence": r.get("evidence"),
                    "science": r.get("science"),
                }
            )
    return out


def focus_reason(code: str) -> dict:
    """Why this exact target became the focus, shown to the user."""
    for r in prescription().get("priority") or []:
        if r.get("code") == code:
            return {"why": r.get("why", ""), "evidence": r.get("evidence"), "source": r.get("source")}
    return {}


# Human names of goals, for choosing a goal without a video.
GOAL_LABELS = {
    "under_rotation": "finish the rotation",
    "basics_rotation": "rotation basics",
    "air_position": "air position",
    "landing_stability": "steady landing",
    "rotation_power": "rotation power",
    "low_height": "jump height",
    "axis_tilt": "air axis",
    "two_foot_landing": "land on one foot",
    "late_check_out": "exit and check-out",
    "stiff_landing_knee": "soft landing knee",
    "fall": "stability, no falls",
    "spin_flexibility": "flexibility for spins",
    "spin_position": "spin positions",
    "balance_control": "one-foot balance",
    "edge_error": "entry edge",
    "step_out": "exit without a step-out",
    "touch_down": "exit without a free-foot touch",
    "hand_down": "exit without a hand down",
    "tilted_axis": "air axis",
}


def goal_label(code: str, lang: str = "en") -> str:
    """Human name of a goal (not the raw code)."""
    return GOAL_LABELS.get(code, code)
