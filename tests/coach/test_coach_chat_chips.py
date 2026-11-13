"""Every suggested chat question gets a meaningful answer from the knowledge base.

Structured answers are built only from the rows of kb/causes.yaml,
kb/drills.yaml, kb/methodology.yaml and the ISU quotes.
"""

from __future__ import annotations

import re

import yaml

from jumpsight_coach import knowledge as K
from jumpsight_core.paths import KB_DIR

CHIPS_EN = ["How do I fix under-rotation?", "Why do my arms open?", "Lutz vs Flip", "Rest between sets"]


def _structured(q):
    for f in (K._lutz_flip_lookup, K._rest_lookup, K._error_fix_lookup):
        r = f(q)
        if r:
            return r
    return None


def test_every_chip_gets_english_structured_answer():
    for q in CHIPS_EN:
        r = _structured(q)
        assert r and r["grounded"] is True and len(r["answer"]) > 80, q
        assert not re.search(r"[\u0400-\u04ff]", r["answer"]), (q, r["answer"][:200])
        assert "do not answer" not in r["answer"]


def test_error_fix_lines_come_from_kb():
    r = K._error_fix_lookup("How do I fix under-rotation?")
    causes = yaml.safe_load((KB_DIR / "causes.yaml").read_text(encoding="utf-8"))["under_rotation"]["causes"]
    texts = {c["text"].strip() for c in causes}
    cause_lines = [row for row in r["answer"].splitlines() if row[:2] in {"1.", "2.", "3."}]
    assert cause_lines
    for line in cause_lines:
        body = line[3:].rsplit(" (", 1)[0]
        assert body in texts, body


def test_unrelated_question_is_not_forced_into_structured_answer():
    assert _structured("What is an axel?") is None
