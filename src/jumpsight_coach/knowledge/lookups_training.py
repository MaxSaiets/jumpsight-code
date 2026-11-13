"""Structured lookups from the training knowledge base: error fixes, drills, safety, methodology, science."""

from __future__ import annotations

from .corpus import _kb_yaml

# Structured answer to "how to fix an error". Similarity search finds the causes of other errors and dosing
# rules for a question like "How to fix under-rotation?", while kb/causes.yaml directly describes the causes
# (with evidence level and source) and kb/drills.yaml has drills with targets: under_rotation. The answer is
# composed deterministically from these two files: no LLM, and each sentence is a line of the knowledge base.
_FIX_INTENT = (
    r"fix|stop|avoid|why|how (?:to|do|can)|improve|correct|what (?:should|can) i do|help|"
    r"cause|reason|get rid"
)
_ERR_WORDS = (
    # "Why is my rotation slow?" has the same causes as under-rotation
    ("under_rotation", r"under[- ]?rot|rotat\w* (?:is |feels )?(?:too )?slow|slow rotat"),
    ("two_foot_landing", r"two[- ]?foot|land\w* on one (?:foot|leg)"),
    ("fall", r"fall"),
    ("stiff_landing_knee", r"stiff"),
    ("late_check_out", r"check[- ]?out"),
    ("axis_tilt", r"axis|tilt"),
    ("low_height", r"height|low jump"),
    ("air_position", r"air position|arms|open|free leg|swings? out"),
    ("landing_stability", r"landing|wobbl|shaky|unstable"),
)
_EVIDENCE_EN = {"A": "strong evidence", "B": "moderate evidence", "C": "weak evidence"}
_ERR_EN = {
    "under_rotation": "under-rotation",
    "two_foot_landing": "two-foot landings",
    "fall": "falls",
    "stiff_landing_knee": "a stiff landing knee",
    "late_check_out": "a late check-out",
    "axis_tilt": "a tilted axis",
    "low_height": "low jumps",
    "air_position": "a loose air position",
    "landing_stability": "unstable landings",
}


def _error_fix_lookup(question: str) -> dict | None:
    import re as _re

    ql = question.lower()
    if not _re.search(_FIX_INTENT, ql):
        return None
    code = next((c for c, pat in _ERR_WORDS if _re.search(pat, ql)), None)
    if code is None:
        return None
    causes = (_kb_yaml("causes.yaml").get(code) or {}).get("causes") or []
    rank = {"A": 0, "B": 1, "C": 2}
    causes = sorted(causes, key=lambda c: rank.get(str(c.get("evidence")), 3))[:3]
    drills = [
        d
        for d in _kb_yaml("drills.yaml")
        if isinstance(d, dict)
        and code in (d.get("targets") or [])
        and d.get("kind") != "do_not_recommend"
        and not d.get("do_not_recommend")
        and not d.get("requires_supervision")
    ]
    drills.sort(key=lambda d: (rank.get(str(d.get("evidence")), 3), d.get("level", 9)))
    drills = drills[:3]
    if not causes and not drills:
        return None
    lines = []
    if causes:
        lines.append(f"Most common causes of {_ERR_EN.get(code, code)}, best-supported first:")
        for i, c in enumerate(causes, 1):
            ev = _EVIDENCE_EN.get(str(c.get("evidence")), "")
            lines.append(f"{i}. {str(c.get('text', '')).strip()}" + (f" ({ev})" if ev else ""))
    if drills:
        lines.append("Drills from the knowledge base that target it:")
        for d in drills:
            dose = str(d.get("dosage") or "")
            ok = str(d.get("success") or "")
            lines.append(f"• {d.get('name')}" + (f" — {dose}" if dose else "") + (f". Success: {ok}" if ok else ""))
    lines.append("A video of your jump shows which cause is yours.")
    srcs = [{"source": str(c.get("source") or "kb/causes.yaml"), "url": "", "score": 1.0} for c in causes]
    srcs += [{"source": f"drill: {d.get('name')}", "url": str(d.get("url") or ""), "score": 1.0} for d in drills]
    return {
        "answer": "\n".join(lines),
        "sources": srcs,
        "grounded": True,
        "structured": "kb_error_fix",
        "error_code": code,
    }


# Position and drill words people ask about by name.
_DRILL_WORDS = (
    r"biell?mann|camel|spiral|backbend|back bend|"
    r"side bend|waltz|landing hops|half rotation|snap drill|snizzle|"
    r"t-stop|toe walking|walking spin|blade (?:guard|cover)"
)


def _drill_lookup(question: str) -> dict | None:
    """A question about a named drill or position: the drills of the KB, easiest first."""
    import re as _re

    m = _re.search(_DRILL_WORDS, question.lower())
    if not m:
        return None
    word = m.group(0)
    drills = [
        d
        for d in _kb_yaml("drills.yaml")
        if isinstance(d, dict)
        and d.get("kind") != "do_not_recommend"
        and not d.get("do_not_recommend")
        and not d.get("requires_supervision")
    ]

    def _hay(d):
        return " ".join([d.get("name", ""), " ".join(d.get("cues") or [])]).lower()

    hit = [d for d in drills if _re.search(word, _hay(d))]
    if not hit:
        return None
    hit.sort(key=lambda d: (int(d.get("level") or 9), d.get("name", "")))
    hit = hit[:6]
    lines = ["Drills from the knowledge base, easiest first:"]
    for d in hit:
        dose = d.get("dosage") or ""
        cue = (d.get("cues") or [""])[0]
        lines.append(
            f"• {d.get('name')} (level {d.get('level')})"
            + (f" — {dose}" if dose else "")
            + (f". Cue: {cue}" if cue else "")
        )
    lines.append("Each drill card in Training shows the steps and a 3D demo where one exists.")
    srcs = [{"source": f"drill: {d.get('name')}", "url": str(d.get("url") or ""), "score": 1.0} for d in hit]
    return {"answer": "\n".join(lines), "sources": srcs, "grounded": True, "structured": "kb_drill"}


# Deterministic answers from our own knowledge base for typical chat questions (knee pain, level, ISU marks,
# warm-up and daily frequency), without LLM and without invention.

_PAIN = r"\b(pain|painful|hurts?|hurting|injur\w*|swollen|swelling|sprain\w*|ache|aching)\b"


def _safety_lookup(question: str) -> dict | None:
    """Pain or injury is not a topic for a drill. First in the chain."""
    import re as _re

    if not _re.search(_PAIN, question.lower()):
        return None
    lines = [
        "Pain is not something a drill should fix, and this app cannot tell what is wrong.",
        "• Stop jumping and other impact work while it hurts. Sharp pain, swelling, a joint "
        "that gives way, or pain that is still there the next morning — see a doctor or a "
        "sports physiotherapist before training again.",
        "• Tell your coach; do not train through pain.",
        "• Normal muscle soreness after a hard session is different: pick “sore” in today's "
        "session and the plan drops to easy steps only.",
    ]
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "safety",
        "sources": [{"source": "JumpSight safety rule", "url": "", "score": 1.0}],
    }


_METHOD = (
    r"warm[- ]?up|cool[- ]?down|every day|daily|how often|times a week|per week|recover|"
    r"how long until|when (?:can|will) i|ready for"
)


def _methodology_lookup(question: str) -> dict | None:
    """Warm-up, frequency, recovery — methodology rules verbatim, with the source."""
    import re as _re

    if not _re.search(_METHOD, question.lower()):
        return None
    meth = _kb_yaml("methodology.yaml") or {}
    ql = question.lower()
    rows = []
    if _re.search(r"warm|cool", ql):
        rows += (meth.get("session_structure") or [])[:2]
    if _re.search(r"how long until|when (?:can|will) i|ready for", ql):
        rows += [r for r in (meth.get("levels") or []) if "PHV" not in str(r.get("text"))][:3]
        rows += (meth.get("progression") or [])[:1]
    if _re.search(r"how many (?:hours|sessions|times)|hours (?:a|per) week|sessions", ql):
        rows += [r for r in (meth.get("levels") or []) if "PHV" not in str(r.get("text"))][:2]
    if _re.search(r"every day|daily|how often|week|recover", ql):
        rows += [r for r in (meth.get("dosage_rules") or []) if "48-72" in str(r.get("text"))]
        rows += [r for r in (meth.get("levels") or []) if "PHV" in str(r.get("text"))]
    rows = [r for r in rows if isinstance(r, dict) and r.get("text")]
    if not rows:
        return None
    texts = [" ".join(str(r["text"]).split()) for r in rows]
    lines = ["From the coaching methodology:"]
    # "how many hours / times a week": the first sentence is the answer itself
    if _re.search(r"how many (?:hours|sessions|times)|hours (?:a|per) week|sessions", ql) and any(
        "2-4" in t for t in texts
    ):
        lines.insert(
            0,
            "In short: the knowledge base gives sessions, not hours — 2-4 sessions a week "
            "at the beginner level"
            + (", with 48-72 h between hard jumping days." if any("48-72" in t for t in texts) else ".")
            + "\n",
        )
    lines += [f"• {x} ({r.get('source', '')})" for x, r in zip(texts, rows)]
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "kb_methodology",
        "sources": [{"source": str(r.get("source") or "kb/methodology.yaml"), "url": "", "score": 1.0} for r in rows],
    }


_SCIENCE_TOPICS = (
    (r"stretch", ("static_stretch_before_power", "warmup_raises_performance")),
    (
        r"\b(kids?|child|children|teen\w*|young|youth|age|growth spurt)\b",
        ("youth_resistance_safe", "growth_spurt_regression"),
    ),
    (r"spin faster|rotate faster|turn faster|faster rotation|more rotation|feel slow", ("air_position_not_takeoff",)),
    (r"confiden|scared|afraid|fear|nervous|new jump", ("challenge_point", "progressive_overload")),
    (r"\bsleep\b", ("sleep_consolidation", "spacing_effect")),
    (
        r"does off[- ]?ice (?:help|work|transfer)|off[- ]?ice.*(?:enough|replace)",
        ("office_transfer_not_automatic", "specificity"),
    ),
)


def _science_lookup(question: str) -> dict | None:
    """Questions answered by the science part of the knowledge base (science.yaml)."""
    import re as _re

    ql = question.lower()
    ids = next((ids for pat, ids in _SCIENCE_TOPICS if _re.search(pat, ql)), None)
    if not ids:
        return None
    by_id = {f["id"]: f for f in (_kb_yaml("science.yaml").get("facts") or [])}
    facts = [(i, by_id[i]) for i in ids if isinstance(by_id.get(i), dict)]
    if not facts:
        return None
    lines = ["What the research behind this app says:"]
    for _, f in facts:
        lines.append(f"• {' '.join(str(f['text']).split())} ({'; '.join(f.get('sources') or [])})")
    if "air_position_not_takeoff" in ids:
        drills = [
            d
            for d in _kb_yaml("drills.yaml")
            if isinstance(d, dict)
            and "air_position" in (d.get("targets") or [])
            and not d.get("do_not_recommend")
            and d.get("kind") != "do_not_recommend"
            and not d.get("requires_supervision")
        ]
        drills.sort(key=lambda d: int(d.get("level") or 9))
        if drills:
            lines.append("Drills for a tighter, faster air position: " + "; ".join(d["name"] for d in drills[:4]) + ".")
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "kb_science",
        "sources": [{"source": "; ".join(f.get("sources") or []), "url": "", "score": 1.0} for _, f in facts],
    }


_OFFICE = r"off[- ]?ice|at home"
_OFFICE_TARGETS = (
    (r"rotat|spin faster|speed", ("rotation_power", "basics_rotation", "under_rotation")),
    (r"height|higher|jump high", ("low_height", "rotation_power")),
    (r"land", ("landing_stability", "two_foot_landing", "stiff_landing_knee")),
    (r"check[- ]?out", ("late_check_out",)),
    (r"arms|air position|tight", ("air_position",)),
    (r"balance", ("balance_control", "landing_stability")),
)


def _office_lookup(question: str) -> dict | None:
    """«Which off-ice drills for …» — the knowledge base's off-ice drills for that target."""
    import re as _re

    ql = question.lower()
    if not _re.search(_OFFICE, ql):
        return None
    targets = next((t for pat, t in _OFFICE_TARGETS if _re.search(pat, ql)), None)
    _frequency = _re.search(r"safe|every day|daily|how often|per week|times a week|recover", ql)
    if not targets and not (
        _re.search(r"exercis|drill|workout|routine|program", ql)
        or (_re.search(r"practi[cs]e|train", ql) and not _frequency)
    ):
        return None
    if not targets:
        # «general off-ice training» — one or two drills per fundamental
        targets = (
            "landing_stability",
            "rotation_power",
            "basics_rotation",
            "low_height",
            "air_position",
            "balance_control",
        )
    drills = [
        d
        for d in _kb_yaml("drills.yaml")
        if isinstance(d, dict)
        and d.get("kind") == "off_ice"
        and not d.get("do_not_recommend")
        and not d.get("requires_supervision")
        and set(targets) & set(d.get("targets") or [])
    ]
    if not drills:
        return None
    drills.sort(key=lambda d: (min(targets.index(t) for t in d["targets"] if t in targets), int(d.get("level") or 9)))
    drills = drills[:6]
    lines = ["Off-ice drills from the knowledge base:"]
    for d in drills:
        dose = d.get("dosage") or ""
        lines.append(f"• {d.get('name')} (level {d.get('level')})" + (f" — {dose}" if dose else ""))
    lines.append("Off-ice gains do not carry over to the ice by themselves — check each one on the ice.")
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "kb_office",
        "sources": [
            {"source": f"drill: {d.get('name')}", "url": str(d.get("url") or ""), "score": 1.0} for d in drills
        ],
    }


def _rest_lookup(question: str) -> dict | None:
    """Rest / sets / reps: the dosage rules of kb/methodology.yaml verbatim, each with its source."""
    import re as _re

    if not _re.search(r"rest|sets?\b|reps?\b|repetition|how many", question.lower()):
        return None
    rules = _kb_yaml("methodology.yaml").get("dosage_rules") or []
    rows = [r for r in rules if isinstance(r, dict) and r.get("text")]
    if not rows:
        return None
    lines = ["Dosage rules from the coaching methodology:"]
    lines += [f"• {' '.join(str(r['text']).split())} ({r.get('source', '')})" for r in rows]
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "kb_dosage",
        "sources": [{"source": str(r.get("source") or "kb/methodology.yaml"), "url": "", "score": 1.0} for r in rows],
    }
