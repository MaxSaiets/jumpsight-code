"""Validators for generated answers: grounded paraphrase check and verbatim excerpt tidying."""

from __future__ import annotations

import re

from .lexical import _lex_stem

_PARA_STOP = frozenset(
    [
        "that",
        "this",
        "with",
        "from",
        "your",
        "have",
        "will",
        "they",
        "them",
        "their",
        "when",
        "what",
        "which",
        "while",
        "into",
        "also",
        "more",
        "most",
        "than",
        "then",
        "very",
        "just",
        "only",
        "each",
        "over",
        "such",
        "been",
        "being",
        "were",
        "does",
        "should",
        "could",
        "would",
        "there",
        "here",
        "about",
        "after",
        "before",
        "because",
    ]
)


def _grounded_paraphrase(answer: str, sources: list[str], min_share: float = 0.7) -> bool:
    """Whether the paraphrase relies on the sources: ≥ 70% of the substantive words of the answer
    (≥ 4 letters, without function words) occur in the supplied excerpts (with rough suffix stripping, as in the lexical search)."""
    # the number must carry the same unit as in the source (640 °/s ≠ 640 seconds)
    src_low = " ".join(sources).lower()
    for num, unit in re.findall(r"(\d+(?:[.,]\d+)?)\s*([a-z°%]+)?", answer.lower()):
        if unit and not re.search(re.escape(num) + r"\s*" + re.escape(unit[:3]), src_low):
            return False
    words = [_lex_stem(w) for w in re.findall(r"[a-z]{4,}", answer.lower()) if w not in _PARA_STOP]
    if len(words) < 3:
        return False
    vocab = {_lex_stem(w) for w in re.findall(r"[a-z]{4,}", " ".join(sources).lower())}
    return sum(1 for w in words if w in vocab) / len(words) >= min_share


def _tidy_excerpt(text: str) -> str:
    """Verbatim excerpt without cut-off edges or wiki markup.

    170 of the 345 English excerpts in the corpus looked like this. Only incomplete sentences at the edges and markup headings are trimmed; no new text is added, the result is a substring of the source.
    """
    import re as _re

    t = _re.sub(r"(={2,})\s*[^=\n]{1,80}?\s*\1", " ", text or "")
    t = " ".join(t.split())
    if len(t) < 120:
        return t
    # trim only a short fragment (≤ 40 % of the excerpt); a longer one keeps the «…»,
    # so that a part that may answer the question is not lost
    if t[:1].islower() or t[:1] in ",;:)":
        m = _re.search(r"[.!?][\"”’)]?\s+(?=[A-Z\"“(])", t)
        t = t[m.end() :] if m and m.end() <= 0.4 * len(t) else "…" + t
    if t[-1:] not in '.!?"”’)':
        ends = list(_re.finditer(r"[.!?][\"”’)]?(?=\s)", t))
        t = t[: ends[-1].end()] if ends and len(t) - ends[-1].end() <= 0.4 * len(t) else t + "…"
    return t.strip()
