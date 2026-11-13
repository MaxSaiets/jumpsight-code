"""Structured lookups from the ISU jump reference: base values, marks, glossary and edge definitions."""

from __future__ import annotations

import json

from jumpsight_core.paths import KB_DIR

# Structured answers from the ISU reference. Factual questions (revolutions, base value, under-rotation
# statistics) are answered deterministically from isu_jump_reference.json (CC BY 4.0), with no embeddings and
# no LLM.
_ISU_REF = KB_DIR / "isu_jump_reference.json"
_JUMP_WORDS = {"axel": "A", "salchow": "S", "toeloop": "T", "toe loop": "T", "loop": "Lo", "flip": "F", "lutz": "Lz"}
_COUNT_WORDS = {"single": 1, "double": 2, "triple": 3, "quad": 4}


def _isu_lookup(question: str) -> dict | None:
    import re as _re

    ql = question.lower()
    intent = _re.search(r"edge|base|value|revolut|under-?rotat|points?\b|how many", ql)
    if not intent:
        return None
    code = None
    m = _re.search(r"\b([1-4])\s*(lz|lo|[afst])\b", ql)
    if m:
        suf = {"a": "A", "f": "F", "s": "S", "t": "T", "lz": "Lz", "lo": "Lo"}[m.group(2)]
        code = f"{m.group(1)}{suf}"
    else:
        jump = next((c for k, c in _JUMP_WORDS.items() if k in ql), None)
        cnt = next((n for k, n in _COUNT_WORDS.items() if k in ql), None)
        if jump and cnt:
            code = f"{cnt}{jump}"
    if not code or not _ISU_REF.is_file():
        return None
    ref = json.loads(_ISU_REF.read_text(encoding="utf-8"))
    j = (ref.get("jumps") or {}).get(code)
    if not j:
        return None
    cnt = int(code[0])
    fam = code[1:]
    revs = j.get("revolutions")
    counts = {1: "Single", 2: "Double", 3: "Triple", 4: "Quadruple"}
    names = {"A": "Axel", "S": "Salchow", "T": "Toe loop", "Lo": "Loop", "F": "Flip", "Lz": "Lutz"}
    nominal = "nominally {revs:g} revolutions."
    axel = "The Axel takes off forwards, so it has half a revolution more than its name implies."
    base = "ISU base value: {value:g}."
    performed = "In the 2016-17 protocols ({n} performances), under-rotation (<) was called in {rate:.0%}."
    edge = "An edge call (e/!) was recorded in {rate:.0%}."
    lines = [f"{counts.get(cnt, cnt)} {names.get(fam, fam)} ({code}): " + nominal.format(revs=revs)]
    if fam == "A":
        lines.append(axel)
    if j.get("base_value") is not None:
        lines.append(base.format(value=j["base_value"]))
    if j.get("times_performed"):
        ur = j.get("under_rotated_rate") or 0
        lines.append(performed.format(n=j["times_performed"], rate=ur))
        if fam in ("Lz", "F") and j.get("edge_call_rate") is not None:
            lines.append(edge.format(rate=j["edge_call_rate"]))
    return {
        "answer": " ".join(lines),
        "sources": [
            {
                "source": "ISU protocols 2016-17 (BuzzFeed News, CC BY 4.0)",
                "url": "https://github.com/BuzzFeedNews/figure-skating-scores",
                "score": 1.0,
            }
        ],
        "grounded": True,
        "structured": "isu_jump_reference",
    }


_ISU_MARKS = (
    r"\bq\b|quarter|downgrad|<<|\bue\b|wrong edge|unclear edge|score ?sheet|"
    # "How do I know if my jump is under-rotated?" asks what it is, not for its causes.
    # "Is my axel under-rotated?" stays with the journal (_my_jump_lookup).
    r"how (?:do|can|would) (?:i|you|we) (?:know|tell|see|check|spot)\b[^?]*under[- ]?rotat|"
    r"what counts as (?:an? )?under[- ]?rotat|"
    # «What does under-rotated mean?» is a definition question
    r"what (?:does|is|are)\b[^?]*under[- ]?rotat|under[- ]?rotat\w*[^?]*\bmean|"
    r"protocol|\bmarks?\b|symbol|technical panel"
)


def _isu_marks_lookup(question: str) -> dict | None:
    """Technical panel marks: q, <, <<, e, !."""
    import re as _re

    if not _re.search(_ISU_MARKS, question.lower()):
        return None
    lines = [
        "How the technical panel marks rotation and edges (ISU, season 2025-26):",
        "• no mark — short by less than 90°: full base value, only GOE can drop.",
        "• q — landed about a quarter short (≈90°): full base value, judges reduce GOE.",
        "• < under-rotated — short by more than 90° but less than 180°: reduced base value.",
        "• << downgraded — short by 180° or more: scored as the jump with one revolution less.",
        "• e — wrong take-off edge (e.g. a Lutz from an inside edge): reduced value and GOE.",
        "• ! — unclear edge: no value reduction, judges may reduce GOE.",
        "A downgrade almost always means the rotation finished on the ice: too little height "
        "or air time, or a late, loose air position. This app measures the rotation in the "
        "air from your video; the panel judges the landing on the ice.",
    ]
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "isu_marks",
        "sources": [
            {
                "source": "ISU Special Regulations & Technical Rules — Single & Pair Skating",
                "url": "https://www.isu.org/figure-skating/rules/fsk-regulations-rules",
                "score": 1.0,
            },
            {
                "source": "ISU S&P Technical Panel Handbook",
                "url": "https://www.isu.org/figure-skating/rules/fsk-handbooks-faq",
                "score": 1.0,
            },
        ],
    }


_GLOSSARY = (
    (
        r"\bgoe\b|grade of execution",
        (
            "GOE (Grade of Execution) is the judges' mark for how well an element was done, on a "
            "scale from -5 to +5. Each step is worth 10% of the element's base value. The highest "
            "and lowest judges' marks are dropped, the rest are averaged, and the result is added "
            "to (or taken from) the base value."
        ),
    ),
    (
        r"combination|combo|sequence|euler",
        (
            "A jump combination is two or more jumps where the landing of one is the take-off of "
            "the next, with no step or turn in between. Because every jump lands on a back outside "
            "edge, the second jump is usually a toe loop or a loop, which take off from that edge; "
            "a half loop (Euler) can link jumps that need a different take-off edge. A jump "
            "sequence is different: jumps linked by hops or steps. This app analyses each jump of "
            "a combination as its own attempt."
        ),
    ),
    # The text comes from the same domain notes as the jump definitions (_JUMPS_EN).
    (
        r"toe[- ]?picks?\b",
        (
            "The toe pick is the row of teeth at the front of the blade. In the three toe jumps "
            "(toe loop, flip, Lutz) the skater taps the free foot's toe pick into the ice to vault "
            "into the air. The three edge jumps (Salchow, loop, Axel) take off from an edge with no "
            "toe pick."
        ),
    ),
)


def _glossary_lookup(question: str) -> dict | None:
    """Judging terms that are absent from the ISU protocol reference."""
    import re as _re

    if not _re.search(r"what(?:'s| is| are| does)|explain|mean|define", question.lower()):
        return None
    hit = next((txt for pat, txt in _GLOSSARY if _re.search(pat, question.lower())), None)
    if not hit:
        return None
    return {
        "answer": hit,
        "grounded": True,
        "structured": "glossary",
        "sources": [
            {
                "source": "ISU Special Regulations & Technical Rules — Single & Pair Skating",
                "url": "https://www.isu.org/figure-skating/rules/fsk-regulations-rules",
                "score": 1.0,
            }
        ],
    }


_EN_COUNT = {"single": 1, "double": 2, "triple": 3, "quad": 4, "quadruple": 4}
_EN_JUMP_CODE = (
    ("toe loop", r"toe[- ]?loop", "T"),
    ("salchow", r"salchow", "S"),
    ("axel", r"axel", "A"),
    ("lutz", r"lutz", "Lz"),
    ("flip", r"flip", "F"),
    ("loop", r"loop", "Lo"),
)


def _harder_lookup(ql: str) -> dict | None:
    """Two jumps with revolution counts -> the base value of both from jump_reference.json."""
    import re as _re

    pat = r"\b(single|double|triple|quad(?:ruple)?)\s+(" + "|".join(p for _, p, _ in _EN_JUMP_CODE) + r")\b"
    codes = []
    for cnt, jump in _re.findall(pat, ql):
        suf = next(c for _, p, c in _EN_JUMP_CODE if _re.fullmatch(p, jump))
        codes.append(f"{_EN_COUNT[cnt]}{suf}")
    if len(codes) != 2 or codes[0] == codes[1] or not _ISU_REF.is_file():
        return None
    ref = json.loads(_ISU_REF.read_text(encoding="utf-8"))
    rows = [(c, (ref.get("jumps") or {}).get(c)) for c in codes]
    if any(not r or r.get("base_value") is None for _, r in rows):
        return None
    (c1, r1), (c2, r2) = rows
    hi, lo = ((c1, r1), (c2, r2)) if r1["base_value"] >= r2["base_value"] else ((c2, r2), (c1, r1))
    lines = [
        f"By base value, the {hi[1]['name']} ({hi[0]}) is worth more: {hi[1]['base_value']} points "
        f"against {lo[1]['base_value']} for the {lo[1]['name']} ({lo[0]}).",
        f"Rotations: {hi[1]['revolutions']} vs {lo[1]['revolutions']}. "
        "Which one is harder for you depends on your technique — the base value is the judges' scale.",
        "Values as scored in ISU competitions 2016–2017; the current ISU scale may differ slightly.",
    ]
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "isu_compare",
        "sources": [{"source": "ISU protocols 2016–2017 (BuzzFeed News data, CC BY 4.0)", "url": "", "score": 1.0}],
    }


def _worth_lookup(question: str) -> dict | None:
    """ "How much is a double Lutz worth?" The base value of ONE jump from the same ISU table.

    The table is already in the image, so the answer does not depend on a search excerpt.
    """
    import re as _re

    ql = question.lower()
    # A bare "how much" must not match ("How much air time do I need for a double Axel?" is not about points):
    # only words about points count; «How do I score a clean…» is about execution, not points.
    if not _re.search(r"\bworth\b|\bpoints?\b|base value|\bscore[sd]?\b", ql):
        return None
    if _re.match(r"\s*how (?:do|can|should|could) (?:i|you|we)\b", ql) and not _re.search(
        r"\bworth\b|\bpoints?\b|base value", ql
    ):
        return None
    pat = r"\b(single|double|triple|quad(?:ruple)?)\s+(" + "|".join(p for _, p, _ in _EN_JUMP_CODE) + r")\b"
    found = _re.findall(pat, ql)
    if len(found) != 1 or not _ISU_REF.is_file():
        return None
    cnt, jump = found[0]
    code = f"{_EN_COUNT[cnt]}" + next(c for _, p, c in _EN_JUMP_CODE if _re.fullmatch(p, jump))
    row = (json.loads(_ISU_REF.read_text(encoding="utf-8")).get("jumps") or {}).get(code)
    if not row or row.get("base_value") is None:
        return None
    lines = [
        f"Base value of the {row['name']} ({code}): {row['base_value']} points, as scored in ISU "
        "competitions 2016–2017; the current ISU scale may differ slightly.",
        "Judges then add or take off GOE for quality, and an under-rotation (<) or downgrade (<<) "
        "lowers the base value itself.",
    ]
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "isu_value",
        "sources": [{"source": "ISU protocols 2016–2017 (BuzzFeed News data, CC BY 4.0)", "url": "", "score": 1.0}],
    }


def _lutz_flip_lookup(question: str) -> dict | None:
    """“Lutz or flip” — the ISU definitions verbatim plus the limit of one camera angle."""
    import re as _re

    ql = question.lower()
    if not (_re.search(r"lutz", ql) and _re.search(r"flip", ql)):
        return None
    lz = (
        'The ISU defines the Lutz jump as "a toe-pick assisted jump with an entrance '
        'from a back outside edge and landing on the back outside edge of the opposite foot".'
    )
    fl = (
        'The ISU defines a flip jump as "a toe jump that takes off from a back inside '
        'edge and lands on the back outside edge of the opposite foot".'
    )
    text = (
        "Both are toe jumps from a backward entry landing on the back outside edge of "
        "the other foot. The only difference is the take-off edge before the toe pick: "
        "Lutz — OUTSIDE edge, flip — INSIDE edge.\n"
        f"ISU definitions (verbatim): {lz} {fl}\n"
        'A Lutz from the inside edge is called a "flutz" and gets an edge call (e/!). '
        "A few degrees of edge cannot be seen reliably from one phone angle, so the "
        "system never names Lutz or flip with high confidence."
    )
    return {
        "answer": text,
        "grounded": True,
        "structured": "isu_lutz_flip",
        "sources": [
            {
                "source": "Wikipedia (en): Figure skating jumps — ISU quotes",
                "url": "https://en.wikipedia.org/wiki/Figure_skating_jumps",
                "score": 1.0,
            }
        ],
    }
