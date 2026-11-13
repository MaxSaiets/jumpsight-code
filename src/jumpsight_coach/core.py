"""Shared core of the recommendation pipelines.

Profile = normalised extract of an analysis result JSON.
Recommendation = one contract for every pipeline.

Invariant: no number in the output is invented. Numbers come from the profile
only; drills come from the knowledge base (kb/) only.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from jumpsight_core.paths import KB_DIR

SOURCE_URLS = {
    "hvfsc": "https://www.hvfsc.com/post/off-ice-rotation-practice-for-figure-skaters-strengthen-jumps-during-quarantine",
    "pwice": "https://www.pwice.com/off-ice-training-exercises-for-figure-skaters/",
    "icoach": "https://icoachskating.com/",
    "ast": "https://adultsskatetoo.com/pages/waltz-jump-guide-beginners",
    "triangulated": "several independent coaching sources (see the drill url)",
    "science": "scientific publications (see the drill url)",
}


# ---------------------------------------------------------------- profile
@dataclass
class Profile:
    """What is known about an attempt from the result JSON (measured only)."""

    file: str
    jump_name: str = "unknown"
    jump_confidence: str = "low"
    revolutions: float | None = None
    rotation_confidence: str = "low"
    verdict: str | None = None  # count_call.call, if present
    air_time_s: float | None = None
    jump_height_m: float | None = None
    errors_found: list[dict] = field(default_factory=list)
    clean: list[str] = field(default_factory=list)
    not_measured: list[dict] = field(default_factory=list)
    quality_notes: list[str] = field(default_factory=list)
    rotation_rate_deg_s: float | None = None  # for comparison with the norms
    # Whether this number is a measurement. The engine refuses the revolution count when its band is wider than
    # half a revolution or includes zero (jumpsight_bridge._rev_usable); the advice must not present p.revolutions
    # as a fact in the LLM prompt or in the skill profile's "best" and "median" when it is not usable.
    rev_usable: bool = True
    rev_unusable_reason: str | None = None
    # The whole-number revolution count (`rotation.rotation_count_call.count`), present in 40 of 105 analyses. It
    # keeps the coach informed about the revolutions where the decimal number is held back.
    nominal_count: int | None = None
    # rotation speed band (°/s); without it, a comparison with the norm cannot call a difference a difference
    rotation_rate_band_deg_s: tuple[float, float] | None = None

    @property
    def error_codes(self) -> list[str]:
        return [e.get("code", "?") for e in self.errors_found]

    def goals(self) -> list[str]:
        """Training goals derived from the measured data (the KB targets dictionary)."""
        g: list[str] = []
        for c in self.error_codes:
            g.append(CODE_ALIASES.get(c, c))
        if self.verdict and any(t in str(self.verdict) for t in ("<", "q", "under")):
            g.append("under_rotation")
        if not g:
            g += self.next_step_goals()
        return list(dict.fromkeys(g))

    def next_step_goals(self) -> list[str]:
        """No errors: where to move on.

        Measured: 65 of 109 results have no error found, and giving all of them the same "base of rotation + position in
        the air" sends a successful jump to beginner drills. "Clean" means not "repeat the basics" but "ready for
        something harder".

        "No errors" and "clean" are different things. If the checks simply did not run (self.clean is empty), one cannot
        claim the jump was successful: the base is returned and the text says so.

        Where to move on is computed against the published norm, not against the data itself. Revolutions = speed ×
        flight time, so comparing the measured speed with the "required one for the same time" is circular: it always
        says "too little speed" and the height branch is unreachable. The reference is therefore external: the rotation
        speed of doubles and triples (Bruening 2018, kb/science.yaml):
          - speed below the norm -> a tighter position in the air and power
          - speed at the norm, but not enough flight time -> height
        """
        if not self.clean:  # checks did not run
            return ["basics_rotation", "air_position"]
        rev, t = self.revolutions, self.air_time_s
        if not rev or not t or t <= 0:
            return ["basics_rotation", "air_position"]
        target = float(int(rev) + 1)  # the next whole revolution
        norm = _rotation_norm_deg_s(target)
        rate = self.rotation_rate_deg_s or (rev / t * 360.0)
        if not norm:
            return ["air_position", "rotation_power", "basics_rotation"]
        if rate < norm:
            return ["air_position", "rotation_power", "basics_rotation"]
        # the speed is already at the norm, so there is not enough time in the air
        return ["low_height", "rotation_power", "basics_rotation"]


_NORMS: dict | None = None


def _rotation_norm_deg_s(target_rev: float) -> float | None:
    """Published rotation speed for this number of revolutions.

    The only source is kb/science.yaml (Bruening 2018, evidence grade A). If there is no norm for this number, None is
    returned and no number is invented: without a reference, the choice of lever is the safest one (position in the air).
    """
    global _NORMS
    if _NORMS is None:
        import yaml

        f = KB_DIR / "science.yaml"
        try:
            _NORMS = (
                (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("norms", {}).get("rotation_speed_deg_s", {})
            )
        except OSError:
            _NORMS = {}
    key = "triples" if target_rev >= 3 else "doubles" if target_rev >= 2 else None
    v = _NORMS.get(key) if key else None
    return float(v) if isinstance(v, (int, float)) else None


# analyzer codes -> knowledge base targets dictionary
CODE_ALIASES = {
    "axis_lean_in_air": "axis_tilt",
    "hard_landing_knee": "stiff_landing_knee",
    "under_rotation_landing": "under_rotation",
    # The four codes of the default analyzer (jumpsight/errors.py) map to targets that have drills, so
    # /recommend has something to return for a real diagnosis.
    "tilted_axis": "axis_tilt",
    "step_out": "late_check_out",
    "touch_down": "landing_stability",
    "hand_down": "landing_stability",
}


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def load_profile(result_json: str | Path) -> Profile:
    from jumpsight_core.evidence import normalize_result

    d = normalize_result(json.loads(Path(result_json).read_text(encoding="utf-8")))

    def _sec(key):  # bad input: a section that is not a dict -> {}
        v = d.get(key)
        return v if isinstance(v, dict) else {}

    rot, ph, jm, er = _sec("rotation"), _sec("phases"), _sec("jump"), _sec("errors")

    # jumpsight (default engine) uses different key names: count_call -> rotation_count_call, and
    # checked_and_clean is a list of rows, not dicts with "code"; reading the older schema directly would lose
    # data or fail on .get() of a string. The ISU symbol (q/</<<) is deliberately not computed by jumpsight, so
    # the verdict stays None and is not replaced by the revolution-count name (goals() looks for "<"/"q"/"under"
    # in the ISU symbol specifically, not in "double").
    if d.get("engine") == "jumpsight":
        clean = list(er.get("checked_and_clean") or [])
        # Not measured is also data: the engine says what it could not do, and that reaches the advice ("X not
        # measured" in pipelines and `_partial` on the screen).
        not_measured = [
            {"code": str(u.get("code") or u), "reason": str(u.get("reason") or "")}
            for u in (er.get("uncertain") or [])
            if isinstance(u, (dict, str))
        ]
        if rot.get("usable") is False and rot.get("reason"):
            not_measured.append({"code": "revolutions", "reason": str(rot.get("reason"))})
    else:
        call = rot.get("count_call")
        call = call if isinstance(call, dict) else {}
        clean = [c.get("code", "?") for c in (er.get("checked_and_clean") or [])]
        not_measured = er.get("not_measured") or []

    p = Profile(
        file=str(result_json),
        jump_name=jm.get("name") or "unknown",
        jump_confidence=jm.get("confidence") or "low",
        revolutions=rot.get("revolutions"),
        rotation_confidence=rot.get("confidence") or "low",
        verdict=(
            None
            if d.get("engine") == "jumpsight"
            else (rot.get("count_call") or {}).get("call")
            if isinstance(rot.get("count_call"), dict)
            else None
        ),
        air_time_s=ph.get("air_time_s"),
        jump_height_m=ph.get("jump_height_m"),
        errors_found=er.get("found") or [],
        clean=clean,
        not_measured=not_measured,
        # the suitability of the number is decided by the engine (jumpsight_bridge._rev_usable) and only carried
        # over here, as into the journal (jobs.py)
        rev_usable=bool(rot.get("usable", True)),
        rev_unusable_reason=rot.get("unusable_reason"),
        nominal_count=_int_or_none(
            (rot.get("rotation_count_call") or {}).get("count")
            if isinstance(rot.get("rotation_count_call"), dict)
            else None
        ),
    )
    # Rotation speed from the engine: the `capture` block is written only by the older engine and is absent in
    # all 76 jumpsight analyses measured, so the comparison with the norm reads the engine's own rate.
    _rate = (rot.get("rate_rev_s") or {}) if isinstance(rot.get("rate_rev_s"), dict) else {}
    if _rate.get("value") is not None:
        p.rotation_rate_deg_s = float(_rate["value"]) * 360.0
        b = _rate.get("band68")
        if isinstance(b, (list, tuple)) and len(b) == 2:
            p.rotation_rate_band_deg_s = (float(b[0]) * 360.0, float(b[1]) * 360.0)
    cap = d.get("capture") or {}
    if cap.get("summary"):
        p.quality_notes.append(str(cap["summary"])[:200])
    rr = cap.get("rotation_rate_rev_s")
    if rr:
        p.rotation_rate_deg_s = float(rr) * 360.0
    return p


# ------------------------------------------------------------ recommendation
@dataclass
class Recommendation:
    pipeline: str
    diagnosis: list[str]  # what is wrong, from MEASURED facts
    why: list[str]  # typical causes (from kb/causes)
    drills: list[dict]  # {id,name,cues,dosage,source,video?}
    week_plan: str
    cautions: list[str]
    confidence: str
    sources: list[str]
    grounded: bool = True  # passed the grounding check
    violations: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


# ------------------------------------------------------------------- KB
@lru_cache(maxsize=4)
def _load_kb_cached(
    drills_path: str, drills_mtime_ns: int, causes_path: str, causes_mtime_ns: int
) -> tuple[list[dict], dict]:
    """Parse a KB revision once; mtimes make edits visible without restart."""
    del drills_mtime_ns, causes_mtime_ns
    drills = yaml.safe_load(Path(drills_path).read_text(encoding="utf-8"))
    causes = yaml.safe_load(Path(causes_path).read_text(encoding="utf-8"))
    return drills, causes


def load_kb() -> tuple[list[dict], dict]:
    drills_path = KB_DIR / "drills.yaml"
    causes_path = KB_DIR / "causes.yaml"
    cached = _load_kb_cached(
        str(drills_path), drills_path.stat().st_mtime_ns, str(causes_path), causes_path.stat().st_mtime_ns
    )
    # Several recommendation pipelines enrich selected dictionaries in place.
    # Keep those request-local while avoiding repeated disk reads and YAML parse.
    return copy.deepcopy(cached)


def pick_drills(
    goals: list[str], drills: list[dict], k: int = 5, level_min: int = 1, level_max: int | None = None
) -> list[dict]:
    """Deterministic pick: cover the goals, from simple levels to complex ones.
    level_min: a clean double is not given beginner drills.
    kind=do_not_recommend is never chosen (negative knowledge)."""
    scored = []
    for dr in drills:
        if dr.get("kind") == "do_not_recommend":
            continue
        if dr.get("level", 1) < level_min:
            continue
        # ceiling: without it a novice could get a level-4 drill because the anti-repeat logic pushes harder
        # ones up
        if level_max is not None and dr.get("level", 1) > level_max:
            continue
        hit = len(set(dr["targets"]) & set(goals))
        if hit:
            scored.append((-hit, dr.get("level", 9), dr["id"], dr))
    scored.sort()
    if not scored and goals and set(goals) != {"basics_rotation", "air_position"}:
        # shared fallback for /today, /recommend and the pipelines:
        # an empty result for a real diagnosis is worse than a basic drill
        return pick_drills(["basics_rotation", "air_position"], drills, k, level_min, level_max)
    by_id = {d["id"]: d for d in drills}
    out, seen_targets = [], set()
    for *_k, dr in scored:
        if len(out) >= k:
            break
        new = set(dr["targets"]) - seen_targets
        if new or len(out) < 3:
            # PREREQUISITE GRAPH: if a drill has a prerequisite and it is not in the
            # output, the prerequisite is given first (a safe progression)
            for pid in dr.get("prerequisites", [])[:1]:
                pre = by_id.get(pid)
                # the prerequisite also respects level_min: a clean double is not
                # handed the novice base "through the back door"
                if pre and pre.get("level", 1) < level_min:
                    continue
                if pre and pre["id"] not in {x["id"] for x in out} and len(out) < k:
                    out.append(pre)
                    seen_targets |= set(pre["targets"])
            if len(out) >= k:
                break
            out.append(dr)
            seen_targets |= set(dr["targets"])
    return out


# ---------------------------------------------------------------- LLM output parsing
def extract_json(text: str) -> dict:
    """Extracts the first VALID JSON object from the LLM response.
    The greedy {.*} broke on any } after the object."""
    dec = json.JSONDecoder()
    for i in range(len(text)):
        if text[i] == "{":
            try:
                obj, _ = dec.raw_decode(text, i)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no JSON in LLM output: {text[:200]}")
