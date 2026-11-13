"""Attempt history (append-only, per user) and progress.

Every finished analysis becomes a record {ts, stem, jump, revolutions,
confidence, errors[]} in the user's history.json under STATE_DIR. Progress is
computed from the history: the trend of revolutions and flight time per jump.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

from jumpsight_core.paths import OUTPUT_DIR, STATE_DIR

OUT = OUTPUT_DIR
HISTORY = STATE_DIR / "history.json"
_lock = threading.Lock()


def _hp():
    from .userctx import user_path

    return user_path(HISTORY)


def _load_hist() -> list[dict]:
    if _hp().exists():
        from jumpsight_core.evidence import normalize_history

        return [normalize_history(row) for row in json.loads(_hp().read_text(encoding="utf-8"))]
    return []


def add_history(result_json: Path) -> dict | None:
    from .core import load_profile

    try:
        p = load_profile(result_json)
    except Exception:
        return None
    # "clean" must not be set when the checks did not run, and the level must not be computed from revolutions
    # that the product itself refuses to show
    import json as _json

    try:
        _raw = _json.loads(Path(result_json).read_text(encoding="utf-8"))
        _cap = _raw.get("capture") or {}
        _sup = ((_cap.get("what_this_clip_supports") or {}).get("revolution_count") or {}).get("supported", True)
        # Measurement error of this clip, carried to the coach so the trend is not drawn as if the numbers were exact.
        _b68 = (_raw.get("rotation") or {}).get("uncertainty_band_68")
        # same shape as in add_history_jumpsight: half-width, not a pair (a pair printed "1.87 ±NaN")
        _band = (
            (float(_b68[1]) - float(_b68[0])) / 2.0
            if isinstance(_b68, (list, tuple)) and len(_b68) == 2 and _b68[0] is not None and _b68[1] is not None
            else (_b68 if isinstance(_b68, (int, float)) else None)
        )
        # Two answers, both with a calibrated percentage: raw probabilities were off by 17 pp; after isotonic
        # calibration the gap is 1.4 pp.
        _rot = _raw.get("rotation") or {}
        _cm = _rot.get("count_model") or {}
        _ip = _rot.get("isu_probabilities") or {}
    except Exception:
        _sup, _band, _cm, _ip = True, None, {}, {}
    rec = {
        "ts": time.time(),
        "stem": result_json.stem.replace("_result", ""),
        "jump": p.jump_name,
        "confidence": p.rotation_confidence,
        "revolutions": p.revolutions if _sup else None,
        "band": _band,
        "count_supported": bool(_sup),
        # "how many revolutions" as a second, independent opinion: it does not
        # inherit the counter's band, so it speaks where the measurement is silent
        "count_named": _cm.get("label"),
        "count_named_pct": _cm.get("confidence_pct"),
        # the ISU symbol's odds instead of a blank "no verdict"
        "isu_most_likely": _ip.get("most_likely"),
        "isu_pct": _ip.get("confidence_pct"),
        "isu_probabilities": _ip.get("probabilities"),
        "air_time_s": p.air_time_s,
        "height_m": p.jump_height_m,
        "errors": p.error_codes,
        # Measured on 76 results: the formula clean = (not error_codes) and not not_measured gave True exactly 0
        # times, because the gate of the ISU verdict is switched off by a constant (src/rotation.py:97 band 0.81
        # against the requirement <0.25 at :652), so not_measured was non-empty in 76/76 and the progress screen
        # showed a permanent zero. "Clean" means the checks RAN and found no errors; how many checks did not run
        # is shown as a separate number, not silently.
        "clean": (not p.error_codes) and bool(p.clean),
        "checks_run": len(p.clean),
        "checks_not_run": len(p.not_measured),
    }
    return _append_hist(rec)


def _file_key(path) -> str | None:
    """Content KEY of the video file: md5(size + first 4 MB + last 4 MB).
    Journal deduplication by stem is not enough: the same clip gets a new stem at each upload (job prefix or
    another file name), and the control video would collect 5+ "attempts" in the journal.
    Partial reading, because clips can be up to 300 MB."""
    try:
        p = Path(path)
        size = p.stat().st_size
        h = hashlib.md5(str(size).encode())
        with open(p, "rb") as f:
            h.update(f.read(4 * 1024 * 1024))
            if size > 8 * 1024 * 1024:
                f.seek(-4 * 1024 * 1024, 2)
                h.update(f.read())
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        return None


def video_source_key(record: dict) -> str | None:
    """Known video file key; the stem and the attempt number are not the source."""
    import re

    explicit = record.get("video_source_key")
    legacy = record.get("file_key")
    match = re.fullmatch(r"([0-9a-f]{32})(?:#a\d+)?", legacy) if isinstance(legacy, str) else None
    derived = match.group(1) if match else None
    if explicit is not None:
        if not isinstance(explicit, str) or not re.fullmatch(r"[0-9a-f]{32}", explicit):
            return None
        return explicit if derived is None or derived == explicit else None
    return derived


def add_history_jumpsight(
    stem: str, result: dict, video_path=None, attempt_id=None, job_id: str | None = None
) -> dict | None:
    """The same journal, for the jumpsight path (src/webapp.py, JS_ENGINE=jumpsight).

    It takes the ready dict from jumpsight_bridge.to_result() directly; no {stem}_result.json file is needed.

    Fields that jumpsight does not compute (isu_pct, count_named_pct, checks_not_run) remain None: they are not invented."""
    from jumpsight_core.evidence import normalize_result

    result = normalize_result(result)
    rot = (result or {}).get("rotation") or {}
    ph = (result or {}).get("phases") or {}
    jm = (result or {}).get("jump") or {}
    errs = (result or {}).get("errors") or {}
    call = rot.get("rotation_count_call") or {}
    found = errs.get("found") or []
    clean_list = errs.get("checked_and_clean") or []
    uncertain = errs.get("uncertain") or []
    execution_state = (
        "assessed" if found else "unavailable" if not clean_list else "partial" if uncertain else "assessed"
    )
    # A fragment is not an attempt. A false-positive window (low-confidence tuck-compression candidate) with ~0.07
    # rev and no count is not a jump, and the coach must not see it in the journal next to real ones. Threshold:
    # no count AND revolutions < 0.3 (a real aborted jump has >0.4 rev in flight even in mocap); the record is
    # written as not measured, and the reason is visible in the server log.
    _rev = rot.get("revolutions")
    # A fall is not a fragment. An aborted attempt with measured errors (a fall, a hand on the ice) often gives
    # no revolutions in flight; treating it as a "window without a count" would drop the fall from the clean
    # share and from skills. A measured error is a measurement: the record goes through the usual path with
    # revolutions=None (excluded from the trend, counted in clean).
    # An entry fragment with a "fall" (rotation without a jump, flight 0.2 s, air_time_s = None) follows the rule
    # of the screen (app.js, fragment): without a jump there is nothing to assess, so "loop or toe loop · Fall"
    # must not count as a fall and a jump. An aborted attempt with a fall and a real flight (0.67 s) does not
    # land here.
    _air_raw = ph.get("air_time_s_raw")
    if (
        ph.get("air_time_s") is None
        and isinstance(_air_raw, (int, float))
        and _air_raw < 0.2
        and call.get("count") is None
    ):
        import sys as _sys

        print(f"[coach-history] not measured '{stem}': entry fragment, raw air {_air_raw:.2f} s", file=_sys.stderr)
        return add_history_unmeasured(
            stem,
            reason="fragment_short_flight",
            job_id=job_id,
            detail="entry fragment, not a jump",
            video_path=video_path,
            attempt_id=attempt_id,
        )
    if call.get("count") is None and not found and (_rev is None or (isinstance(_rev, (int, float)) and _rev < 0.3)):
        # A record must not disappear without a trace: the user would see fewer analyses than videos uploaded and not
        # know which ones vanished. A false-positive window must still not stand in the trend next to real
        # measurements, so the record is written with outcome="not_measured": it is visible in the journal with its
        # reason, and it does not enter the trend or clean_pct (see progress()).
        import sys as _sys

        print(f"[coach-history] not measured '{stem}': rev={_rev}, no count call", file=_sys.stderr)
        return add_history_unmeasured(
            stem,
            reason="fragment_no_count",
            job_id=job_id,
            # Text without the variable part, so each rev value does not become a separate string.
            detail="window without a rotation count",
            video_path=video_path,
            attempt_id=attempt_id,
        )
    # the journal stores the band as a scalar (half-width; /progress averages it as a number); jumpsight gives
    # [lo, hi], so it is converted here, otherwise progress() fails on "int + list"
    _b68 = rot.get("uncertainty_band_68")
    _band_scalar = (_b68[1] - _b68[0]) / 2.0 if isinstance(_b68, (list, tuple)) and len(_b68) == 2 else _b68
    # The journal is not more honest than the screen. When the name is not determined (low confidence and 3+
    # equal alternatives: the 'undetermined' rule), the journal says "not determined", not the top-1: the coach
    # reads the list as facts. The revolution count itself is already filtered through rev_usable.
    _unc = (
        jm.get("name_display") is None
        and (jm.get("confidence") == "low")
        and len(jm.get("alternatives") or []) >= 3
        and bool(jm.get("name"))
    )
    rec = {
        "ts": time.time(),
        "stem": stem,
        "job": job_id,
        "jump": jm.get("name"),
        "name_uncertain": _unc,
        "name_confidence": jm.get("confidence"),
        "name_display": jm.get("name_display"),
        "name_is_family": bool(jm.get("name_is_family")),
        "confidence": rot.get("confidence"),
        "revolutions": rot.get("revolutions"),
        "band": _band_scalar,
        "count_supported": bool(rot.get("measured")),
        "count_named": call.get("name"),
        # The journal is not more honest than the screen, part two. The rev_usable flag guards a decimal revolution
        # count, but the count in words ("double") also goes into the journal and into the reverse link, so it is
        # marked when it came not from the width band but from the kinematic head or the agreement of two channels.
        # The trend, records and the "said/true" pair must not read the estimate as a measurement.
        "count_estimated": bool(call.get("estimated")),
        "count_estimate_kind": call.get("estimate_kind"),
        "count_confidence": call.get("confidence"),
        "count_named_pct": None,
        "isu_most_likely": rot.get("isu_verdict"),
        "isu_pct": None,
        "isu_probabilities": None,
        "air_time_s": ph.get("air_time_s"),
        "height_m": ph.get("jump_height_m"),
        # the ±68% height band: without it, a record in "Progress" cannot state the height accuracy
        "height_band_m": ph.get("jump_height_ci68"),
        "errors": [x.get("code") for x in found],
        # the confidence of each found error (the engine's tier); records without these fields are treated as unknown
        # by aggregates
        "errors_conf": {x.get("code"): x.get("confidence") or "low" for x in found if x.get("code")},
        "clean": (not found) and bool(clean_list) and not uncertain,
        "execution_state": execution_state,
        "errors_uncertain": uncertain,
        "errors_checked_clean": list(clean_list),
        "checks_run": len(clean_list),
        "checks_not_run": None,
        # An explicit marker, not a guess from the presence of revolutions: aggregates
        # must be able to tell a measurement from the trace of a failed attempt.
        "outcome": "measured",
        # the revolution count stays in the record, but the trend and records take only those where the uncertainty
        # band is narrower than half a revolution and does not include zero. The engine decides
        # (jumpsight_bridge._rev_usable); here it is only carried over into the journal.
        "rev_usable": bool(rot.get("usable")),
        "rev_unusable_reason": rot.get("unusable_reason"),
        "engine": "jumpsight",
        "error_checks_version": result.get("error_checks_version"),
    }
    # The dedup key is the file content + the attempt number within the clip (in a clip with two
    # jumps both records are legitimate; they are not duplicates).
    fk = _file_key(video_path) if video_path else None
    if fk:
        rec["video_source_key"] = fk
        rec["file_key"] = f"{fk}#a{attempt_id}" if attempt_id is not None else fk
    return _append_hist(rec)


def add_history_unmeasured(
    stem: str,
    reason: str,
    detail: str = "",
    video_path=None,
    attempt_id=None,
    name: str | None = None,
    job_id: str | None = None,
) -> dict | None:
    """A trace from an upload from which nothing was measured.

    A video in which a jump was not found or not measured must still leave a trace in the journal, so the person can
    see which uploads gave no measurement and why.

    Such a record is deliberately incomplete: `revolutions` is absent, `clean` is absent, `outcome="not_measured"`, and the reason is given as text. It goes into the journal; it does not go into the trend or into the share of clean attempts (see progress()).
    """
    rec = {
        "ts": time.time(),
        "stem": stem,
        "job": job_id,
        "jump": name,
        "confidence": None,
        "revolutions": None,
        "band": None,
        "count_supported": False,
        "count_named": None,
        "count_named_pct": None,
        "isu_most_likely": None,
        "isu_pct": None,
        "isu_probabilities": None,
        "air_time_s": None,
        "height_m": None,
        "errors": [],
        "clean": None,
        "checks_run": 0,
        "checks_not_run": None,
        "outcome": "not_measured",
        "reason": reason,
        "reason_detail": detail,
        "engine": "jumpsight",
    }
    fk = _file_key(video_path) if video_path else None
    if fk:
        rec["video_source_key"] = fk
        rec["file_key"] = f"{fk}#a{attempt_id}" if attempt_id is not None else fk
    return _append_hist(rec)


# The suitability threshold for the revolution count is the same as in the engine (src/jumpsight_bridge:
# REV_BAND_MAX_WIDTH / REV_BAND_MIN_LOWER). It is needed for records without the rev_usable field: the journal
# stores the band as a scalar (half-width), so suitability is computed from what exists. Trusting such a record
# silently would keep building the card "PERSONAL BESTS · up to 1.53 rotations" from a number with a ±0.92 band.
_REV_BAND_MAX_WIDTH = 0.5
_REV_BAND_MIN_LOWER = 0.0


def rev_is_usable(rec: dict) -> bool:
    """Whether the revolution count in this record is a measurement."""
    flag = rec.get("rev_usable")
    if flag is not None:
        return bool(flag)
    rev, band = rec.get("revolutions"), rec.get("band")
    if not isinstance(rev, (int, float)):
        return False
    if not isinstance(band, (int, float)):
        return False  # without a band, suitability cannot be established
    lo, width = rev - band, 2.0 * band
    return lo > _REV_BAND_MIN_LOWER and width < _REV_BAND_MAX_WIDTH


def _append_hist(rec: dict) -> dict | None:
    with _lock:
        hist = _load_hist()
        # One clip, one record. Deduplication within a time window does not hold: /recommend writes to history on
        # every view of the result, so a repeat visit minutes later would create a second "attempt" (measured: two
        # records of one jump 354 s apart made /progress count total=2 and narrow the error from 0.26 to 0.184: one
        # jump sold itself as two independent attempts). The key is the clip itself (stem), not the time. Keeping the
        # first record forever would break the same invariant: when the same file is re-analyzed and the result
        # changes, the old record would stay in /progress and the day plan, silently diverging from the answer screen.
        # Overwriting the record with the same stem is not a duplicate (same measurement) and always shows the
        # freshest truth.
        fk = rec.get("file_key")
        hist = [h for h in hist if h.get("stem") != rec["stem"] and not (fk and h.get("file_key") == fk)]
        hist.append(rec)
        # The write is atomic: a plain write_text interrupted midway would leave the attempts journal half-written,
        # and the next read would raise instead of returning data. Same helper as the rest of the user's state.
        from .statefile import write_json

        write_json(_hp(), hist)
    return rec


def history() -> list[dict]:
    return list(reversed(_load_hist()))[:50]


MEDIAN_BAND = 0.28  # median uncertainty_band_68 over the 60 clips of the corpus


def jump_is_resolved(record: dict) -> bool:
    """A pair/family or a refusal does not prove a specific top-1 skill."""
    if record.get("jump") in (None, "", "?", "not resolved", "None"):
        return False
    if any(record.get(key) in (True, "True", "true") for key in ("name_uncertain", "name_is_family")):
        return False
    display = record.get("name_display")
    return not (isinstance(display, str) and "/" in display)


def execution_clean_state(record: dict) -> bool | None:
    """An unmeasurable execution is neither clean nor dirty."""
    if record.get("errors"):
        return False
    if record.get("execution_state") in ("partial", "unavailable"):
        return None
    return record.get("clean") in (True, "True", "true")


def error_check_state(record: dict, code: str) -> bool | None:
    """Found / checked without error / unknown, for a single code."""
    if record.get("outcome") == "not_measured":
        return None
    if code in (record.get("errors") or []):
        return True
    uncertain = record.get("errors_uncertain") or []
    if any((item.get("code") if isinstance(item, dict) else item) == code for item in uncertain):
        return None
    if code in (record.get("errors_checked_clean") or []):
        return False
    return None


def goal_check_state(record: dict, codes: set[str], *, require_all: bool = False) -> bool | None:
    """Independent channels of a goal require all the negative checks."""
    states = [error_check_state(record, code) for code in codes]
    if any(state is True for state in states):
        return True
    if states and (all(state is False for state in states) if require_all else any(state is False for state in states)):
        return False
    return None


def progress() -> dict:
    """Trends for the chart: for each jump a list of (ts, revolutions), the share of clean attempts, the consecutive streak, and an HONEST verdict about the change.

    A single attempt proves nothing: the system's own error is ±0.28 revolution. A simulation showed that with ZERO real change, a chart of individual attempts draws a "trend" of >=0.2 revolution in 47% of cases. Therefore:
      - points are grouped by day (the day's median), as the coach does;
      - the mean's error band/sqrt(n) goes with the point;
      - a change is called a change only if it exceeds MDC95.
    """
    hist = _load_hist()
    # Deduplicate on read as well as on write: files written before dedup-on-write existed may still contain
    # duplicates, which would count one jump twice and narrow the mean's error from 0.26 to 0.184. The regression
    # test catches exactly this: progress must not become "more precise" because the person opened their own
    # analysis twice.
    seen_stems: set[str] = set()
    uniq = []
    for h in hist:
        s = h.get("stem")
        if s in seen_stems:
            continue
        if s:
            seen_stems.add(s)
        uniq.append(h)
    hist = uniq
    by_jump: dict[str, list] = {}
    for h in hist:
        if h.get("outcome") == "not_measured":
            continue
        if h.get("revolutions") is None:
            continue
        # A number whose band is wider than half a revolution or includes zero does not enter the trend. Records
        # without the field stay in the trend, because they cannot be recomputed retrospectively and silently dropping
        # data is worse than leaving it visible.
        if not rev_is_usable(h):
            continue
        # One scale on the chart only: records of the older engine measured something else (a shortened window: 1.09
        # vs 1.53 on the same clip) and on one curve with fresh ones would draw a false "regression". They stay
        # visible in the attempts journal, not in the trend.
        if h.get("engine") != "jumpsight":
            continue
        # The trend "by jump" may not rely on a name that the system did not determine, otherwise the "salchow"
        # curve collects other people's attempts. The revolution count in such a record stays valid, but there is
        # nothing to group it by.
        if not jump_is_resolved(h):
            continue
        day = int(h["ts"] // 86400)
        by_jump.setdefault(h["jump"], []).append((day, h["ts"], h["revolutions"], h.get("band") or MEDIAN_BAND))

    trend: dict[str, list] = {}
    change: dict[str, dict] = {}
    for jump, rows in by_jump.items():
        days: dict[int, list] = {}
        for d, ts, rev, band in rows:
            days.setdefault(d, []).append((ts, rev, band))
        pts = []
        for d in sorted(days):
            vals = sorted(x[1] for x in days[d])
            n = len(vals)
            med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
            band = sum(x[2] for x in days[d]) / n
            pts.append([days[d][0][0], round(med, 2), round(band / (n**0.5), 3), n])
        trend[jump] = pts
        if len(pts) >= 2:
            # Compare windows at the edges (up to 3 days each), not one day from each edge. Measured on a simulated
            # history of 200 attempts over 100 days with an embedded true gain of +0.60 revolution, first day vs last day
            # gave delta 0.46 at MDC95 0.55 and the verdict "no change": the two edge days hold 2 attempts each, so the
            # mean's error is wide there and 98% of the data went unused. The mean's error falls as sqrt(N) over a
            # window, and real progress becomes visible without weakening the criterion: MDC95 is computed from the same
            # errors.
            w = max(1, min(3, len(pts) // 4))
            head, tail = pts[:w], pts[-w:]

            def _mean(g):
                return sum(p[1] for p in g) / len(g)

            def _sem(g):
                # the mean of w independent daily means
                return (sum(p[2] ** 2 for p in g) ** 0.5) / len(g)

            delta = _mean(tail) - _mean(head)
            mdc = 1.96 * ((_sem(head) ** 2 + _sem(tail) ** 2) ** 0.5)
            change[jump] = {
                "delta": round(delta, 2),
                "mdc": round(mdc, 2),
                "significant": abs(delta) > mdc,
                "n_attempts": sum(p[3] for p in pts),
                "n_days": len(pts),
                # it is visible what was compared with what: the verdict must be
                # checkable, not "the system decided so"
                "window_days": w,
                "base": round(_mean(head), 2),
                "now": round(_mean(tail), 2),
            }

    # Traces of unmeasured attempts are visible in the journal, but they do not count toward the share of clean
    # ones: "not measured" is not "performed dirty", and counting them would worsen clean_pct on every clip from
    # which nothing was extracted.
    measured = [h for h in hist if h.get("outcome") != "not_measured"]
    states = [execution_clean_state(h) for h in measured]
    clean = [c for c in states if c is not None]
    streak = 0
    for c in reversed(states):
        if c is True:
            streak += 1
        else:
            break
    # The share is only among assessed executions; partial checks prove neither a clean nor a not-clean
    # execution. The share's error is binomial with the Agresti–Coull correction (k+2)/(n+4): the plain Wald SE at
    # 3 of 3 clean would give "100% ±0.0", a zero error on three attempts.
    n = len(clean)
    k = sum(clean)
    if n:
        p_ = (k + 2) / (n + 4)
        se = round(100 * (p_ * (1 - p_) / (n + 4)) ** 0.5, 1)
    else:
        se = None
    return {
        "trend": trend,
        "change": change,
        "total": len(measured),
        "clean_assessed_total": n,
        "clean_pct": round(100 * k / n) if n else None,
        "clean_pct_se": se,
        # jumpsight records leave checks_not_run=None (the engine does not count it, we do not invent), and
        # .get(key, 0) does not cover an explicit None, so the sum treats "not measured" as 0 (the record itself
        # stays None)
        "checks_not_run": sum(h.get("checks_not_run") or 0 for h in hist),
        # How many uploads left a trace but gave no measurement: without it, "5 attempts in the journal" after
        # seven videos would read as "two vanished by themselves".
        "not_measured": len(hist) - len(measured),
        # How many records have a revolution count that is not a measurement.
        "rev_not_usable": sum(1 for h in measured if not rev_is_usable(h)),
        "streak": streak,
    }
