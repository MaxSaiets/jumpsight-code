"""Early numbers: what the engine has already measured before the full response,
derived from the `attempts.confirmed` and `attempt.timing` events.
"""

from __future__ import annotations


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def early_from_confirmed(ev: dict, fps) -> dict | None:
    """Early numbers: what the engine has already measured before the full response.

    The `attempts.confirmed` event carries the number of analyzed attempts (`count`)
    and the candidate windows in frames. Seconds come only from the fps in
    `media.probe` of this same video; no fps means no seconds (30 is not
    substituted). The `attempt_id` of the first window is its position in `windows`
    + 1 (the engine numbers this way), so the flight time from `attempt.timing`
    attaches to exactly the displayed window.
    """
    count = ev.get("count")
    if not (_num(count) and count >= 0):
        return None
    early: dict = {"attempts": int(count)}
    if not (_num(fps) and fps > 0):
        return early
    first = None
    for i, w in enumerate(ev.get("windows") or []):
        if not isinstance(w, dict) or w.get("status") not in ("confirmed", "low_confidence"):
            continue
        if not (_num(w.get("f0")) and _num(w.get("f1")) and w["f1"] > w["f0"] >= 0):
            continue
        if first is None or w["f0"] < first[1]["f0"]:
            first = (i, w)
    if first is not None:
        i, w = first
        early["first_window_s"] = [round(w["f0"] / fps, 2), round(w["f1"] / fps, 2)]
        early["attempt_id"] = i + 1
    return early


def early_with_timing(early: dict | None, ev: dict) -> dict | None:
    """Flight time / take-off / landing from `attempt.timing`, ONLY if the event
    carries them (the measurement is not `absent`) and only for the attempt of the
    displayed window. Nothing is computed here. Returns a NEW dict (already published
    projections are not changed retroactively) or None if there is nothing to add."""
    if not isinstance(early, dict) or "attempt_id" not in early:
        return None
    if ev.get("attempt_id") != early["attempt_id"] or "air_s" in early:
        return None
    add: dict = {}
    air = ev.get("air_time_s")
    if isinstance(air, dict) and air.get("status") != "absent" and _num(air.get("value")) and air["value"] > 0:
        add["air_s"] = round(float(air["value"]), 3)
    for key in ("takeoff_s", "landing_s"):
        if _num(ev.get(key)) and ev[key] >= 0:
            add[key] = round(float(ev[key]), 3)
    return {**early, **add} if add else None
