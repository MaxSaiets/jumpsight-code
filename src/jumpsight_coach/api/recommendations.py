"""POST /recommend: deterministic advice from an analysis result."""

from __future__ import annotations

import hashlib
import json
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jumpsight_core.paths import KB_DIR, OUTPUT_DIR

from ..pipelines import p8_program, p9_ensemble
from .common import _require_stem_access, _valid_stem

router = APIRouter()


_RECO_CACHE: dict[str, dict] = {}  # md5(result)+lang -> answer


def kb_version() -> str:
    h = hashlib.md5()
    for f in ("drills.yaml", "causes.yaml", "programs.yaml"):
        fp = KB_DIR / f
        if fp.exists():
            h.update(fp.read_bytes())
    return h.hexdigest()[:10]


class RecommendIn(BaseModel):
    result: dict
    lang: str = "en"
    stem: str | None = None  # if set, write to history


# --- human layer: short advice without technical detail ---
_SIMPLE = {
    "under_rotation": (
        "Under-rotation",
        "You open up too early — hold a tight air position until the rotation is done",
    ),
    "two_foot_landing": ("Two-foot landing", "Learn to trust your landing leg — train one-foot landing balance"),
    "axis_tilt": ("Axis lean", "Stay in a straight column — level axis from head to skating foot"),
    "stiff_landing_knee": ("Stiff landing knee", "Absorb the landing with your knee — soft, like a spring"),
    "fall": ("Fall", "Step back: simpler jump and basics first — then return"),
    "late_check_out": ("Late check-out", "Stop the rotation with your shoulders right after landing"),
    "_clean": ("Clean attempt!", "No errors found — keep the level and progress gradually"),
    # the limit of the system, never an order to the skater (PRODUCT.md no. 4)
    "_lowconf": (
        "Hard to measure this video",
        "the system could not measure everything in these frames — it is most precise when the skater is large in frame and the video is 60 fps",
    ),
    "_partial": (
        "Partially measured",
        "What could be checked looks clean; some checks were not possible on this footage",
    ),
}

# Human names instead of technical ones
_VERDICT_HUMAN = {
    "not resolved": "Jump could not be named",
    "unknown": "Jump could not be named",
}


def _sec(d, key: str) -> dict:
    """Section of the input JSON if it is a dict, otherwise {}.

    The input comes from the client, so the section's shape is checked, not assumed: `{"rotation": "trash"}`
    must not become a 500. The same helper exists in core.load_profile.
    """
    v = (d or {}).get(key) if isinstance(d, dict) else None
    return v if isinstance(v, dict) else {}


def _count_supported(result: dict) -> bool:
    """Whether a revolution count can be named on this clip.

    The `capture` block is written only by the older engine (it is absent in all 76 analyses measured in
    out/). When it is absent, the engine's own report decides whether the number is usable
    (rotation.usable / unusable_reason).
    """
    cap = _sec(result, "capture")
    w = (cap.get("what_this_clip_supports") or {}) if isinstance(cap.get("what_this_clip_supports"), dict) else {}
    w = w.get("revolution_count") or {}
    if isinstance(w, dict) and w:
        return bool(w.get("supported", True))
    rot = _sec(result, "rotation")
    if rot.get("usable") is not None:
        return bool(rot.get("usable"))
    return True


def _count_blocker(result: dict, lang: str = "en") -> str:
    """Why revolutions are not measured - in plain words, with the fact from the clip."""
    if _count_supported(result):
        return ""
    # Name only the condition that actually failed: quoting the height and the
    # fps regardless of what broke once produced a passed condition as the
    # reason for the refusal. Three conditions (capture.what_this_clip_supports
    # .revolution_count.why): fps >= 24, skater height > 200 px, rotation
    # rate < fps/4.
    cap = result.get("capture") or {}
    px = cap.get("skater_height_px")
    fps = cap.get("fps")
    rate = cap.get("rotation_rate_rev_s")
    ceil = cap.get("rotation_ceiling_rev_s")
    bad = []
    if fps and fps < 23.9:  # tolerance for NTSC 23.976
        bad.append(f"frame rate {fps:.1f} fps, need 24+")
    if px and px <= 200:
        bad.append(f"the skater is {px:.0f} px tall, need over 200")
    if rate and ceil and rate >= ceil:
        bad.append(
            f"rotation {rate:.1f} rev/s is at or above the counter ceiling "
            f"{ceil:.1f} rev/s (a quarter of the frame rate): one turn per "
            f"two frames cannot be told from standing still"
        )
    head = "Revolutions cannot be measured on this clip"
    if not bad:
        # none of the three capture conditions failed: the measurement itself failed, and we say so
        # instead of inventing a culprit
        return head + (
            ". The capture itself is fine; the rotation signal in the pose data was not usable on this clip."
        )
    tail = ". The measurement works best with the skater larger in frame or at a higher frame rate."
    return head + ": " + "; ".join(bad) + tail


def _human_verdict(name: str, lang: str = "en") -> str:
    return _VERDICT_HUMAN.get(str(name).strip().lower(), name)


def _user_view(p, lang: str = "en") -> dict:
    """What the user sees: one headline + one main advice + the focus.

    "Clean attempt" is shown only when the checks really ran; otherwise the
    third state "partially measured" is used.
    """
    codes = [
        c
        for c in ("fall", "axis_tilt", "under_rotation", "two_foot_landing", "stiff_landing_knee", "late_check_out")
        if c in [str(e) for e in p.goals()]
    ]
    if p.rotation_confidence == "low" and not p.error_codes:
        key = "_lowconf"
    elif codes:
        key = codes[0]
    elif p.not_measured:
        key = "_partial"
    else:
        key = "_clean"
    head, advice = _SIMPLE[key]
    return {"headline": head, "advice": advice, "focus_code": key.strip("_")}


@router.post("/recommend")
def recommend(inp: RecommendIn, request: Request) -> dict:
    import tempfile

    from .. import fitness as _fi
    from .. import goal as _go
    from .. import skills as _sk
    from ..core import load_profile
    from ..userctx import current_uid
    from ..userctx import user_path as _up

    if inp.stem:
        if not _valid_stem(inp.stem):
            raise HTTPException(400, "bad analysis id")
        if (OUTPUT_DIR / f"{inp.stem}_result.json").exists():
            _require_stem_access(inp.stem, request)
    # The cache key covers everything the answer depends on besides the result JSON: the uid (the cache is
    # not shared between users) and _stamp, the mtime of the current user's skill, fitness and goal profile
    # files. build()/p9_ensemble use the level, persistent gaps and fitness gates, which change with the
    # survey or a fitness test and not with the result JSON. The save functions always overwrite these
    # files, so any such change moves mtime, changes _stamp and therefore the md5 key.
    _stamp = "|".join(
        str(_up(x).stat().st_mtime_ns) if _up(x).exists() else "0" for x in (_sk.PROFILE, _fi.PROFILE, _go.STORE)
    )
    key = hashlib.md5(
        (json.dumps(inp.result, sort_keys=True) + inp.lang + (current_uid() or "") + _stamp).encode()
    ).hexdigest()
    if key in _RECO_CACHE:  # optimization: answer cache
        return _RECO_CACHE[key]
    # load_profile reads a file, so we give it a temporary one (the contract stays a file
    # for the CLI, and a dict for the API)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(inp.result, tf, ensure_ascii=False)
        tmp = tf.name
    try:
        p = load_profile(tmp)
        r9 = p9_ensemble(p)
        r8 = p8_program(p)
    except Exception as ex:  # broken input -> honest 422, not 500
        raise HTTPException(status_code=422, detail=f"invalid result JSON: {ex}") from None
    finally:
        os.unlink(tmp)
    out = {
        "verdict": p.verdict or _human_verdict(p.jump_name, inp.lang),
        "diagnosis": r9.diagnosis,
        "why": r9.why,
        "drills": r9.drills,
        "program": {"title": r8.diagnosis[-1] if r8.diagnosis else "", "days": r8.week_plan.split(" | ")},
        "cautions": r9.cautions,
        "confidence": r9.confidence,
        "sources": r9.sources,
        "user_view": _user_view(p, inp.lang),
        "metrics": {
            "revolutions": p.revolutions,
            "air_time_s": p.air_time_s,
            "jump_height_m": p.jump_height_m,
            "rotation_rate_deg_s": p.rotation_rate_deg_s,
            "jump_name": _human_verdict(p.jump_name, inp.lang),
            # The analyzer itself says whether the clip allows counting revolutions at all. If not, the number
            # is not shown as a fact: it comes from a noisy pose and misleads.
            # how many jumps were in the clip versus how many were analyzed
            "jumps_on_clip": _sec(inp.result, "jumps_on_clip"),
            "count_supported": _count_supported(inp.result),
            "count_blocker": _count_blocker(inp.result, inp.lang),
            # Two answers with a calibrated percentage. Raw probabilities were off by 17 pp (at a claimed 95%
            # the model was right 70% of the time); after isotonic calibration the gap is 1.4 pp, and only
            # for that reason is a percentage shown at all.
            # The frame-quality gate applies to them too: both are computed from the same revolutions, so
            # when the clip does not meet the gate (skater at 187 px where 200 is required) they stay
            # silent together with the measurement.
            "count_model": (
                (_sec(inp.result, "rotation").get("count_model") or {})
                if _count_supported(inp.result)
                else {
                    "available": False,
                    "why": "this clip does not support revolution counting, and this model reads the same measurement",
                }
            ),
            "isu_probabilities": (
                (_sec(inp.result, "rotation").get("isu_probabilities") or {})
                if _count_supported(inp.result)
                else {"available": False, "why": "the ISU bands are computed from the same revolution count"}
            ),
            # What the number is backed by: an error band and the evidence for it, so the screen does not
            # show bare numbers ("0.81 rev, 0.43 s air, 0.04 m height") next to "double, 45%".
            "revolutions_range": (_sec(inp.result, "rotation").get("revolutions_range")),
            "uncertainty_band_rev": (_sec(inp.result, "rotation").get("uncertainty_band_68")),
            # Two independent height estimates; their agreement is the main evidence that the frame
            # scale was recovered correctly.
            "height_from_curvature_m": (_sec(inp.result, "phases").get("jump_height_m_from_flight_curvature")),
            "height_methods_differ_m": (_sec(inp.result, "phases").get("jump_height_methods_differ_m")),
            "torso_m": (_sec(inp.result, "phases").get("skater_torso_length_m")),
            "physically_plausible": (_sec(inp.result, "phases").get("physically_plausible")),
            "not_a_jump_because": (_sec(inp.result, "phases").get("not_a_jump_because")),
            # Revolutions broken down by element: the revolutions in the air differ from the revolutions of
            # the whole element ("double/triple"), which include the ice spin-up and the touch-down at the
            # exit. Two different quantities must not share one label.
            "rotation_breakdown": (
                (_sec(inp.result, "rotation").get("rotation_breakdown") or {}) if _count_supported(inp.result) else {}
            ),
            # Cross-checked against the published scale and the behavior of the instrument on optical mocap.
            "external_check": _sec(inp.result, "external_check"),
            "isu_reference": _sec(inp.result, "isu_reference"),
        },
        "meta": {"kb_version": kb_version(), "pipeline": "p9+p8", "lang": inp.lang},
    }
    if inp.stem:  # viewing = a history record
        from ..jobs import add_history

        f = OUTPUT_DIR / (inp.stem + "_result.json")
        if f.exists():
            add_history(f)
    _RECO_CACHE[key] = out
    if len(_RECO_CACHE) > 500:
        _RECO_CACHE.pop(next(iter(_RECO_CACHE)))
    return out
