"""Lexical (BM25) retrieval over the corpus, used while the embedding model loads."""

from __future__ import annotations

import re

from .index import _digest, _load

_LEX: dict = {}
_LEX_STOP = frozenset(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "is",
        "are",
        "was",
        "be",
        "do",
        "does",
        "did",
        "how",
        "what",
        "why",
        "when",
        "which",
        "who",
        "i",
        "my",
        "me",
        "you",
        "your",
        "it",
        "its",
        "this",
        "that",
        "with",
        "at",
        "by",
        "from",
        "can",
        "should",
        "will",
        "would",
        "there",
        "their",
        "as",
        "not",
        "no",
        "if",
        "so",
        "than",
        "then",
        "into",
        "about",
    ]
)
_LEX_SUFFIX = ("ations", "ation", "ions", "ion", "ings", "ing", "ers", "ors", "ed", "er", "or", "es", "s")


def _lex_stem(w: str) -> str:
    """Crude suffix stripping: invented / inventor -> invent."""
    if len(w) > 5:
        for s in _LEX_SUFFIX:
            if w.endswith(s) and len(w) - len(s) >= 4:
                return w[: -len(s)]
    return w


def _lex_tokens(text: str) -> list[str]:
    return [_lex_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _LEX_STOP]


def _lexical_hits(question: str, k: int = 5) -> list[dict] | None:
    """BM25 over the corpus without the model, while the embedding model loads.

    None if no meaningful word of the question occurs in the corpus."""
    import math as _math

    rows, _ = _load()
    dig = _digest(rows)
    if _LEX.get("digest") != dig:
        _LEX.clear()
    if not _LEX:
        docs = [_lex_tokens(r.get("text", "")) for r in rows]
        df: dict[str, int] = {}
        for d in docs:
            for w in set(d):
                df[w] = df.get(w, 0) + 1
        n = len(docs)
        _LEX.update(
            rows=rows,
            digest=dig,
            docs=docs,
            avg=(sum(map(len, docs)) / max(1, n)),
            idf={w: _math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()},
        )
    q = [w for w in dict.fromkeys(_lex_tokens(question)) if w in _LEX["idf"]]
    if not q:
        return None
    k1, b = 1.5, 0.75
    scored = []
    for i, d in enumerate(_LEX["docs"]):
        if not d:
            continue
        tf: dict[str, int] = {}
        for w in d:
            tf[w] = tf.get(w, 0) + 1
        s, hit = 0.0, 0
        for w in q:
            f = tf.get(w)
            if f:
                hit += 1
                s += _LEX["idf"][w] * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / _LEX["avg"]))
        if s > 0:
            # first how many DIFFERENT question words the passage has, then BM25
            scored.append((hit, s, i))
    if not scored:
        return None
    scored.sort(reverse=True)
    rows = _LEX["rows"]
    return [{**rows[i], "score": round(s, 3), "retrieval": "lexical"} for _, s, i in scored[:k]]
