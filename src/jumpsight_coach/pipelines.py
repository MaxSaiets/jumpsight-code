"""Recommendation pipelines. One input (Profile) and one output (Recommendation).

P1 rules    - deterministic: errors -> causes -> drills, template text
P5 case     - no LLM: the nearest clean attempts in the corpus are the reference,
              recommendations come from the largest measured deviations
P7 semantic - P1 diagnosis + embedding search over the knowledge base
P8 program  - a 14-day course from kb/programs.yaml
P9 ensemble - the product answer: P5 diagnosis + P1 drills, ranked by evidence
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from jumpsight_core.paths import KB_DIR, OUTPUT_DIR

from .core import CODE_ALIASES, SOURCE_URLS, Profile, Recommendation, load_kb, load_profile, pick_drills


# ----------------------------------------------------------------- P1
def p1_rules(p: Profile) -> Recommendation:
    drills_kb, causes_kb = load_kb()
    goals = p.goals()
    diagnosis, why, cautions = [], [], []
    aborted = False  # axis tilt >30° = failed attempt
    for e in p.errors_found:
        code = e.get("code", "")
        if code in ("axis_lean_in_air", "axis_tilt"):
            nums = [float(x) for x in __import__("re").findall(r"\d+\.?\d*", str(e.get("measured", "")))[:1]]
            if nums and nums[0] > 30:
                aborted = True
                diagnosis.append(
                    f"axis tilt {nums[0]:.0f}° - the attempt was aborted in the air; "
                    f"this is a bail-out, not working technique"
                )
                continue
        diagnosis.append(
            f"{code}: {e.get('measured', 'measured')}"
            + (f" (threshold {e['threshold']})" if e.get("threshold") else "")
        )
    if p.verdict:
        diagnosis.append(f"rotation verdict: {p.verdict}")
    if not diagnosis:
        diagnosis.append("no measured errors found; building rotation fundamentals")
    if aborted:
        goals = ["basics_rotation", "landing_stability", "axis_tilt"]
        cautions.append(
            "attempt was bailed - go back to a simpler jump and the basics instead of polishing this attempt"
        )
    # causes: those measured on THIS video come first; unmeasured ones are marked
    found_codes = set(p.error_codes)
    for g in goals:
        cs = (causes_kb.get(g, {}) or {}).get("causes", [])
        measured = [c for c in cs if any(fc in str(c.get("visible_in", "")) for fc in found_codes)]
        typical = [c for c in cs if c not in measured]
        for c in measured[:2]:
            why.append(f"[{g}] {c['text']}")
        for c in typical[: 2 - len(measured[:2])]:
            why.append(f"[{g}] possible cause (a coach should confirm): {c['text']}")
    # level: the SKILL PROFILE comes first (survey + measured over several
    # videos), and only as a fallback a guess from a single jump
    lvl_min = 1
    try:
        from .skills import profile as _skill_profile

        sp = _skill_profile()
        if sp.get("level"):
            lvl_min = max(1, min(3, sp["level"] - 1))
            cautions.append(f"level from the profile: {sp['level']}")
    except Exception:
        pass
    if (
        lvl_min == 1
        and not p.errors_found
        and any(t in p.jump_name.lower() for t in ("double", "triple", "quad", "2", "3", "4"))
    ):
        lvl_min = 2
    drills = pick_drills(goals, drills_kb, level_min=lvl_min)
    if not p.errors_found and lvl_min > 1:
        cautions.append("no errors found - a plan that keeps the difficulty up, not the basic level")
    if p.rotation_confidence == "low":
        cautions.append("measurement confidence is low - the advice is generic")
    for nm in p.not_measured[:2]:
        cautions.append(f"not measured {nm.get('code')}: {str(nm.get('reason'))[:90]}")
    # SCIENCE (science.yaml): spin-rate norms as an external reference
    sci = _science()
    rate = getattr(p, "rotation_rate_deg_s", None)
    # A norm is keyed by jump class, not by a decimal number: p.revolutions is withheld on most clips by the
    # honesty rules (the comparison never fired in 146 attempts). The Bruening 2018 norm is defined for double and
    # triple jumps, a class that also comes from the whole-number count the engine names more often
    # (nominal_count).
    _key = None
    if p.revolutions is not None and getattr(p, "rev_usable", True) and p.revolutions >= 1.5:
        _key = "triples" if p.revolutions >= 2.5 else "doubles"
    elif getattr(p, "nominal_count", None) in (2, 3, 4):
        _key = "triples" if p.nominal_count >= 3 else "doubles"
    if rate and _key:
        norms = sci.get("norms", {}).get("rotation_speed_deg_s", {})
        key = _key
        if norms.get(key):
            # The band decides whether there is a difference: a gap is not stated as a fact when the measurement
            # band covers the norm.
            _norm = float(norms[key])
            _b = getattr(p, "rotation_rate_band_deg_s", None)
            _what = "triples" if key == "triples" else "doubles"
            if _b and _b[0] <= _norm <= _b[1]:
                diagnosis.append(
                    f"rotation speed {rate:.0f}°/s (band {_b[0]:.0f}-"
                    f"{_b[1]:.0f}) - this measurement does not differ from the "
                    f"{_what} norm of ~{_norm:.0f}°/s (Bruening 2018)"
                )
            else:
                _side = "below" if rate < _norm else "above"
                _band_txt = f" (band {_b[0]:.0f}-{_b[1]:.0f})" if _b else ""
                diagnosis.append(
                    f"rotation speed {rate:.0f}°/s{_band_txt} - {_side} "
                    f"the published {_what} norm of ~{_norm:.0f}°/s (Bruening 2018)"
                )
    # negative knowledge: what NOT to do for these goals (level A evidence)
    for dr in drills_kb:
        if dr.get("kind") == "do_not_recommend" and set(dr.get("targets", [])) & set(goals):
            cautions.append(f"NOT recommended: {dr['name']} — {dr['cues'][0]}")
    # off-ice transfer is not automatic (Bruening 2006)
    if any(d.get("kind") == "off_ice" for d in drills):
        cautions.append(
            "off-ice gains do not transfer to the ice automatically - verify every drill on ice (Bruening 2006)"
        )
    # week focus: ONE priority error (guidance hypothesis)
    prio = [c for c in sci.get("priority_order", []) if c in {CODE_ALIASES.get(x, x) for x in p.error_codes}]
    focus = (
        f"WEEK FOCUS - one error: {prio[0]} (the full review goes in the session summary, not after every jump). "
        if prio
        else ""
    )
    week = focus + "Week: " + "; ".join(f"{d['name']} - {d.get('dosage', '2-3 sets')}" for d in drills[:3])
    # the app does not lead to an external provider: no routes to outside courses or paid 1:1 lessons
    return Recommendation(
        pipeline="p1_rules",
        diagnosis=diagnosis,
        why=why,
        drills=[_slim(d) for d in drills],
        week_plan=week,
        cautions=cautions,
        confidence=p.rotation_confidence,
        sources=sorted({SOURCE_URLS.get(d["source"], d.get("url", "")) for d in drills}),
    )


def _science() -> dict:
    import yaml

    f = KB_DIR / "science.yaml"
    return yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {}


def _slim(d: dict) -> dict:
    """Drill fields that reach the browser.

    Steps exist in 47 of 51 drills in the knowledge base and are passed through.
    """
    keys = (
        "id",
        "name",
        "cues",
        "dosage",
        "source",
        "video",
        "url",
        "steps",
        "success",
        "mistakes_to_avoid",
        "evidence",
        "level_min",
        "targets",
    )
    return {k: d[k] for k in keys if k in d}


# ----------------------------------------------------------------- P5
def _features(p: Profile) -> np.ndarray | None:
    """Comparison vector; NaN where a quantity is NOT measured.

    The honesty rules withhold decimal revolutions on most clips (103 of 105 analyses have low confidence), while flight
    time is measured in 74 analyses, so distance is computed over the axes present in both attempts.
    """
    if p.air_time_s is None:
        return None  # without flight there is nothing to compare
    rev = p.revolutions if (p.revolutions is not None and p.rev_usable) else np.nan
    return np.array([rev, p.air_time_s, p.jump_height_m or np.nan, len(p.errors_found)], dtype=float)


def p5_case(p: Profile, corpus_dir: str | Path | None = None) -> Recommendation:
    drills_kb, causes_kb = load_kb()
    me = _features(p)
    refs = []
    for f in Path(corpus_dir or OUTPUT_DIR).glob("*_result.json"):
        if Path(f).resolve() == Path(p.file).resolve():
            continue
        try:
            q = load_profile(f)
        except Exception:
            continue
        # A reference is a clean attempt with measured flight. A confidence gate on revolutions would reject 103
        # of 105 analyses, including the measured flight time. Revolutions are compared separately below, and
        # only where they are usable.
        if q.errors_found:
            continue
        v = _features(q)
        if v is not None:
            refs.append((q, v))

    # reference = the same jump AND the same revolution class (|delta| < 0.75) -
    # otherwise a single would be compared with a double and "advised" to add a full revolution
    def _same_class(q) -> bool:
        """Same revolution class: by measured revolutions, otherwise by the whole-number
        count, otherwise it cannot be established (and then the numbers are not compared)."""
        if p.revolutions is not None and q.revolutions is not None and p.rev_usable and q.rev_usable:
            return abs(q.revolutions - p.revolutions) < 0.75
        if p.nominal_count is not None and q.nominal_count is not None:
            return p.nominal_count == q.nominal_count
        return False

    same = [(q, v) for q, v in refs if q.jump_name == p.jump_name and _same_class(q)]
    same_jump_refs = len(same) >= 3
    if same_jump_refs:
        refs = same
    diagnosis, why = [], []
    if me is None or not refs:
        # Say why there is no comparison, so the same «not enough measurements» does not appear both where there
        # is no flight and where there is no corpus
        if me is None:
            diagnosis.append("flight time was not measured on this clip - no case comparison")
        diagnosis.append("not enough measurements for a case comparison")
        drills = pick_drills(p.goals() or ["basics_rotation"], drills_kb)
        return Recommendation(
            pipeline="p5_case",
            diagnosis=diagnosis,
            why=why,
            drills=[_slim(d) for d in drills],
            week_plan="start with the basic steps",
            cautions=[],
            confidence="low",
            sources=sorted({SOURCE_URLS[d["source"]] for d in drills}),
        )
    scale = np.array([1.0, 0.5, 0.5, 1.0])

    def _dist(v):
        d = (v - me) * scale
        ok = np.isfinite(d)
        if not ok.any():
            return float("inf")
        # we normalise by the number of shared axes, otherwise an attempt with fewer
        # measured quantities would look «closer»
        return float(np.linalg.norm(d[ok]) / np.sqrt(ok.sum()))

    dists = [_dist(v) for _, v in refs]
    order = [i for i in np.argsort(dists)[:3] if np.isfinite(dists[i])]
    near = [refs[i][0] for i in order]
    if not near:
        diagnosis.append("nothing to compare with: the corpus has no clean attempts sharing measured values")
        drills = pick_drills(p.goals() or ["basics_rotation"], drills_kb)
        return Recommendation(
            pipeline="p5_case",
            diagnosis=diagnosis,
            why=why,
            drills=[_slim(d) for d in drills],
            week_plan="start with the basic steps",
            cautions=[],
            confidence="low",
            sources=sorted({SOURCE_URLS[d["source"]] for d in drills}),
        )
    _revs = [r.revolutions for r in near if r.revolutions is not None and r.rev_usable]
    ref_rev = float(np.median(_revs)) if _revs else None
    ref_air = float(np.median([r.air_time_s for r in near]))
    goals = list(p.goals())
    # Safety: revolutions may only be compared with references of the same jump, otherwise a single would be
    # advised to «spin like a double» = over-rotation
    if (
        same_jump_refs
        and ref_rev is not None
        and p.revolutions is not None
        and p.rev_usable
        and p.revolutions < ref_rev - 0.2
    ):
        diagnosis.append(f"revolutions {p.revolutions:.2f} vs {ref_rev:.2f} in clean {p.jump_name} attempts")
        goals += ["under_rotation", "rotation_power"]
    if same_jump_refs and p.air_time_s < ref_air - 0.05:
        diagnosis.append(f"flight time {p.air_time_s:.2f} s vs {ref_air:.2f} s for the references")
        goals += ["low_height"]
    if not same_jump_refs:
        diagnosis.append(
            f"fewer than 3 clean {p.jump_name} references in the corpus - no numeric comparison (honest limit)"
        )
    for e in p.errors_found:
        diagnosis.append(f"{e.get('code')}: {str(e.get('measured'))[:80]}")
    if not diagnosis:
        diagnosis.append("profile is within the reference clean attempts")
    goals = list(dict.fromkeys(goals)) or ["basics_rotation"]
    for g in goals[:3]:
        for c in (causes_kb.get(g, {}) or {}).get("causes", [])[:1]:
            why.append(f"[{g}] {c['text']}")
    drills = pick_drills(goals, drills_kb)
    week = "Week: " + "; ".join(f"{d['name']} - {d.get('dosage', '2-3 sets')}" for d in drills[:3])
    return Recommendation(
        pipeline="p5_case",
        diagnosis=diagnosis,
        why=why,
        drills=[_slim(d) for d in drills],
        week_plan=week,
        cautions=[f"references: {len(refs)} clean attempts in the corpus"],
        confidence=p.rotation_confidence,
        sources=sorted({SOURCE_URLS[d["source"]] for d in drills}),
    )


# ----------------------------------------------------------------- P7
def p7_semantic(p: Profile) -> Recommendation:
    """P1 diagnosis, then an embedding search over the whole knowledge base
    to add the causes that match the errors found."""
    from .embed import search

    base = p1_rules(p)
    goals = p.goals()
    hits = search(f"{p.jump_name} {' '.join(goals)} {'; '.join(base.diagnosis)[:200]}", k=12)
    drills_kb, _ = load_kb()
    chosen = pick_drills(goals, drills_kb, k=5)
    # only causes that concern the errors found
    found = set(p.error_codes) | set(goals)
    extra_causes = [
        f"[{h.get('code', '')}] {h.get('text', '')}"
        for h in hits
        if h.get("type") == "cause" and h.get("code") in found
    ]
    why = list(dict.fromkeys(base.why + extra_causes[:1]))
    srcs = sorted({SOURCE_URLS.get(d.get("source"), d.get("url", "")) for d in chosen})
    return Recommendation(
        pipeline="p7_semantic",
        diagnosis=base.diagnosis,
        why=why,
        drills=[_slim(d) for d in chosen],
        week_plan=base.week_plan,
        cautions=base.cautions,
        confidence=base.confidence,
        sources=srcs,
    )


# ----------------------------------------------------------------- P8
def p8_program(p: Profile) -> Recommendation:
    """Course program, as in real courses: Week -> Day ->
    drills with dosage, with entry/exit gates. No LLM at all."""
    import yaml

    progs = yaml.safe_load((KB_DIR / "programs.yaml").read_text(encoding="utf-8"))
    drills_kb, _ = load_kb()
    by_id = {d["id"]: d for d in drills_kb}
    base = p1_rules(p)  # diagnosis / causes / cautions
    goals = p.goals()
    prog = next((pr for pr in progs if pr["goal"] in goals), progs[-1])
    day_lines, used_ids = [], []

    def _block_of(d: dict) -> str:
        """Session block (NCCP): power, while fresh, goes in main; flexibility -
        only in the cool-down (LESSON-SPEC §1, ordering rules §7.6-7.7)."""
        if d.get("block"):
            return d["block"]
        if set(d.get("targets", [])) & {"low_height", "rotation_power"}:
            return "power"
        if "spin_flexibility" in d.get("targets", []):
            return "cooldown"
        return "skill"

    for wi, week in enumerate(prog["weeks"], 1):
        for di, day in enumerate(week["days"], 1):
            if day == "rest":
                day_lines.append(f"W{wi}D{di}: rest")
            elif isinstance(day, str):
                day_lines.append(f"W{wi}D{di}: {day}")
            else:
                # 5-block session anatomy (NCCP): warm-up -> specific
                # -> main (new skills while fresh) -> volume -> cool-down
                ds = [by_id[i] for i in day if i in by_id]
                used_ids += [d["id"] for d in ds]
                power = [d for d in ds if _block_of(d) == "power"]
                cool = [d for d in ds if _block_of(d) == "cooldown"]
                skill = [d for d in ds if d not in power and d not in cool]
                parts = ["Warm-up 3-5 min (easy jog, arm circles)"]
                if skill:
                    parts.append(f"Specific warm-up: {skill[0]['name']} at half effort")
                main = (skill or power)[:2]
                parts.append("Main: " + "; ".join(f"{d['name']} ({d.get('dosage', '')})" for d in main))
                vol = [d for d in power if d not in main]
                if vol:
                    parts.append(
                        "Volume: " + "; ".join(f"{d['name']} ({d.get('dosage', '')}, rest 60-120 s)" for d in vol)
                    )
                parts.append("Cool-down 2-3 min: " + (cool[0]["name"] if cool else "static stretching"))
                day_lines.append(f"W{wi}D{di}: " + " → ".join(parts))
    drills = [_slim(by_id[i]) for i in dict.fromkeys(used_ids) if i in by_id][:8]
    cautions = base.cautions + [
        f"entry gate: {prog['gate_in']}",
        f"exit gate: {prog['gate_out']}",
        "difficulty rule: success on ~2 of 3 attempts = the right level; "
        ">2/3 - make it harder, <1/3 - step back (challenge point)",
    ]
    if prog.get("maturation_note"):
        cautions.append(f"growth spurt: {prog['maturation_note']}")
    return Recommendation(
        pipeline="p8_program",
        diagnosis=base.diagnosis + [f"program: {prog['title']}"],
        why=[prog.get("science", "")] + base.why[:2],
        drills=drills,
        week_plan=" | ".join(day_lines),
        cautions=cautions,
        confidence=base.confidence,
        sources=sorted({SOURCE_URLS.get(by_id[i]["source"], by_id[i].get("url", "")) for i in used_ids if i in by_id}),
    )


# ----------------------------------------------------------------- P9
def p9_ensemble(p: Profile) -> Recommendation:
    """Ensemble without an LLM: P5 diagnosis (references + norms) plus drills from P1 and P7, merged and ranked by evidence level (A>B) and video availability."""
    r1, r5 = p1_rules(p), p5_case(p)
    drills_kb, _ = load_kb()
    by_name = {d["name"]: d for d in drills_kb}
    pool = {x["name"]: x for x in (r1.drills + r5.drills)}

    def rank(item):
        d = by_name.get(item["name"], {})
        return ({"A": 0, "B": 1, "C": 2}.get(d.get("evidence", "C"), 2), 0 if item.get("video") else 1)

    drills = sorted(pool.values(), key=rank)[:5]
    diagnosis = list(dict.fromkeys(r5.diagnosis + r1.diagnosis))
    # no truncation of names: otherwise localization cannot match the full string
    ev_note = [
        "drill evidence: "
        + ", ".join(f"{x['name']}={by_name.get(x['name'], {}).get('evidence', '?')}" for x in drills[:3])
    ]
    return Recommendation(
        pipeline="p9_ensemble",
        diagnosis=diagnosis,
        why=list(dict.fromkeys(r1.why + r5.why))[:4],
        drills=drills,
        week_plan=r1.week_plan,
        cautions=list(dict.fromkeys(r1.cautions + r5.cautions + ev_note)),
        confidence=r1.confidence,
        sources=sorted(set(r1.sources) | set(r5.sources)),
    )


PIPELINES = {
    "p1_rules": p1_rules,
    "p5_case": p5_case,
    "p7_semantic": p7_semantic,
    "p8_program": p8_program,
    "p9_ensemble": p9_ensemble,
}
