"""Structured lookups from the jump definitions: what a jump is, how jumps compare and their order."""

from __future__ import annotations

import json

from .corpus import _kb_yaml
from .lookups_isu import _ISU_REF, _harder_lookup

# The six jumps (for a skater who rotates counter-clockwise; for the other
# direction the feet are mirrored).
_JUMPS_EN = {
    "axel": (
        "Axel",
        "edge jump",
        "The only jump that takes off forwards, from a forward outside edge, facing the direction of travel — "
        "so it has an extra half revolution: a single is 1.5, a double 2.5, a triple 3.5. "
        "The free leg swings up and forward; landing is on the back outside edge of the other foot.",
    ),
    "salchow": (
        "Salchow",
        "edge jump",
        "Take-off from a back inside edge on a bent knee, with no toe pick. The free leg starts behind "
        "and swings wide around and forward — that wide circular swing is its signature. "
        "Landing on the back outside edge of the other foot.",
    ),
    "waltz": (
        "Waltz jump",
        "beginner jump",
        "A half-revolution jump: take-off forwards from the outside edge of one foot and landing "
        "backwards on the back outside edge of the other foot. It is the first jump most skaters "
        "learn and the base of the Axel's extra half turn.",
    ),
    "loop": (
        "Loop",
        "edge jump",
        "Take-off and landing on the same foot, on a back outside edge, with no toe pick and very little "
        "free-leg movement: the skater seems to glide on one foot and lift off.",
    ),
    "toe loop": (
        "Toe loop",
        "toe jump",
        "Glide backwards on the right outside edge and pick into the ice with the left toe; "
        "land on the right foot, back outside edge. Usually the first jump learned with a toe pick.",
    ),
    "flip": (
        "Flip",
        "toe jump",
        "Glide backwards on the left inside edge and pick with the right toe; land on the right foot, "
        "back outside edge.",
    ),
    "lutz": (
        "Lutz",
        "toe jump",
        "Glide backwards on the left outside edge — usually a longer straight backward glide than the flip — "
        "and pick with the right toe; land on the right foot, back outside edge.",
    ),
}
_JUMP_Q = (
    r"what(?:'s| is) an? |explain|take[- ]?off|how (?:do you|to) do|describe|"
    r"how (?:do i|to|can i) (?:land|learn|do|get)|"
    # "how to start to lutz" style questions
    r"how (?:do i|to|can i|should i) (?:start|begin|master|practi[cs]e|improve)|first steps|"
    r"\b(?:start|begin|learn)\w*\b[^?]*\b(?:waltz|toe[- ]?loop|axel|salchow|lutz|flip|loop)"
)


def _jump_def_lookup(question: str) -> dict | None:
    """'What is a toe loop', 'explain the salchow takeoff': definitions from the knowledge base."""
    import re as _re

    ql = question.lower()
    if not _re.search(_JUMP_Q, ql):
        return None
    key = next(
        (k for k in ("waltz", "toe loop", "toe-loop", "axel", "salchow", "lutz", "flip", "loop") if k in ql), None
    )
    if not key:
        return None
    name, fam, body = _JUMPS_EN["toe loop" if key == "toe-loop" else key]
    art = "an" if fam[0] in "aeiou" else "a"
    text = (
        f"{name} — {art} {fam}. {body}\n"
        "Edges and feet are for a skater who rotates counter-clockwise (most skaters); "
        "for clockwise skaters the feet are mirrored."
        + (
            ""
            if key == "waltz"
            else " A jump is told apart only by its take-off — flight and landing look almost the same for all six."
        )
    )
    if _re.search(r"land|learn|get|start|begin|first steps|practi[cs]e", ql):
        # "how to learn / land": definition + the base's preparatory drills
        drills = [
            d
            for d in _kb_yaml("drills.yaml")
            if isinstance(d, dict)
            and set(d.get("targets") or []) & {"basics_rotation", "under_rotation", "landing_stability"}
            and not d.get("do_not_recommend")
            and d.get("kind") != "do_not_recommend"
            and not d.get("requires_supervision")
            and int(d.get("level") or 9) <= 2
        ]
        drills.sort(key=lambda d: int(d.get("level") or 9))
        text += (
            "\nNew jumps are learned on the ice with a coach. Lead-in drills from the "
            "knowledge base: " + "; ".join(d["name"] for d in drills[:5]) + "."
            if drills
            else "\nNew jumps are learned on the ice with a coach."
        )
    return {
        "answer": text,
        "grounded": True,
        "structured": "jump_definition",
        "sources": [{"source": "JumpSight domain notes (ISU jump definitions)", "url": "", "score": 1.0}],
    }


_NAMES_RE = (
    ("toe loop", r"toe[- ]?loop"),
    ("salchow", r"salchow"),
    ("axel", r"axel"),
    ("lutz", r"lutz"),
    ("flip", r"flip"),
    ("loop", r"loop"),
)


_ORDER_Q = (
    r"\b(?:easiest|simplest|hardest|most difficult)\b[^?]*\bjump|\bfirst jumps?\b|"
    r"which jumps? (?:comes?|is|should i learn) (?:after|next|before)|\bjumps? (?:comes? )?(?:after|before) the\b|"
    r"\border\b[^?]*\bjumps?|\bjumps?\b[^?]*\border\b"
)


def _order_lookup(question: str) -> dict | None:
    """«Which jump is easiest», «what comes after a Salchow» — ISU scale and domain notes.

    The knowledge base has no learning order (coaches differ), so the answer says so. It gives the judges' scale (base
    value of single jumps) and the jumps most skaters start with, not an encyclopedia excerpt.
    """
    import re as _re

    ql = question.lower()
    if not _re.search(_ORDER_Q, ql) or not _ISU_REF.is_file():
        return None
    if _re.search(r"combination|combo|sequence|video|analys", ql):  # «first jump of a cascade/video» — not about this
        return None
    jumps = json.loads(_ISU_REF.read_text(encoding="utf-8")).get("jumps") or {}
    singles = [(code, row) for code, row in jumps.items() if code.startswith("1") and row.get("base_value") is not None]
    if len(singles) < 6:
        return None
    _short = {"1T": "toe loop", "1S": "Salchow", "1Lo": "loop", "1F": "flip", "1Lz": "Lutz", "1A": "Axel"}
    singles.sort(key=lambda cr: (cr[1]["base_value"], list(_short).index(cr[0]) if cr[0] in _short else 9))
    scale = ", ".join(f"{_short.get(c, r.get('name'))} {r['base_value']}" for c, r in singles)
    lines = [
        "Most skaters start with the waltz jump (half a turn); the toe loop is usually the first "
        "jump learned with a toe pick.",
        f"By ISU base value of the single jumps — the judges' scale of difficulty: {scale} points "
        "(ISU competitions 2016–2017; the current scale may differ slightly). The Axel is the "
        "hardest single: it takes off forwards, so it has an extra half turn.",
        "The knowledge base has no single prescribed learning order after that — it differs between "
        "coaches, so ask yours what comes next for you.",
    ]
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "jump_order",
        "sources": [
            {"source": "ISU protocols 2016–2017 (BuzzFeed News data, CC BY 4.0)", "url": "", "score": 1.0},
            {"source": "JumpSight domain notes (ISU jump definitions)", "url": "", "score": 1.0},
        ],
    }


def _compare_lookup(question: str) -> dict | None:
    """«How does an Axel differ from a Lutz» — two definitions side by side, with one shared hint."""
    import re as _re

    ql = question.lower()
    if not _re.search(r"differen|\bvs\.?\b|versus|compar|harder|more difficult|worth more", ql):
        return None
    # «is 2A harder than 3S» — base value of both from the ISU protocols
    if _re.search(r"harder|more difficult|worth more|more points", ql):
        hit = _harder_lookup(ql)
        if hit:
            return hit
    rest, found = ql, []
    for key, pat in _NAMES_RE:
        if _re.search(pat, rest):
            found.append(key)
            rest = _re.sub(pat, " ", rest)
    if len(found) != 2:
        return None
    lines = []
    for key in found:
        name, fam, body = _JUMPS_EN[key]
        lines.append(f"• {name} ({fam}): {body}")
    lines.append("Only the take-off tells jumps apart; flight and landing look almost the same for all six.")
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "jump_compare",
        "sources": [{"source": "JumpSight domain notes (ISU jump definitions)", "url": "", "score": 1.0}],
    }
