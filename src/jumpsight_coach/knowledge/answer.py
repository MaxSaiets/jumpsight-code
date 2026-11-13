"""ask(): structured lookups first, then retrieval and an LLM answer validated against the sources."""

from __future__ import annotations

import re
import sys

import numpy as np

from .. import embed
from .corpus import _BUILD_HINT, CORPUS
from .index import _FALLBACK_READY, _FALLBACK_WAIT_S, _load, _m, warm_fallback
from .lexical import _lexical_hits
from .lookups_app import (
    _about_lookup,
    _app_lookup,
    _my_jump_lookup,
    _personal_data_lookup,
    _personal_lookup,
    _scope_lookup,
    _sourced_lookup,
    _unsure_lookup,
)
from .lookups_isu import _glossary_lookup, _isu_lookup, _isu_marks_lookup, _lutz_flip_lookup, _worth_lookup
from .lookups_jumps import _compare_lookup, _jump_def_lookup, _order_lookup
from .lookups_training import (
    _drill_lookup,
    _error_fix_lookup,
    _methodology_lookup,
    _office_lookup,
    _rest_lookup,
    _safety_lookup,
    _science_lookup,
)
from .validate import _grounded_paraphrase, _tidy_excerpt

_PERSONAL = ("my", "me", "mine", "myself")


def _user_context() -> str:
    """The user's own data (all analyses, today's plan, sessions, coach)."""
    try:
        from ..user_snapshot import context_text

        return context_text()
    except Exception:  # noqa: BLE001
        return ""


_MESSAGES = {
    "excerpt": "Source excerpt without generated advice.",
    "empty_answer": "The model returned an empty answer. An available excerpt or explanation is shown.",
    "unverified_numbers": "Numbers in the answer were not found in the sources. An available excerpt or explanation is shown.",
    "unsupported_claim": "The wording could not be verified against a source excerpt. An excerpt or explanation is shown.",
    "no_answer": (
        "I can't give a direct answer to that one yet. I can help with: learning a jump "
        "(“How do I start the Lutz?”), fixing errors like under-rotation or falls, "
        "drills, rest and warm-up, ISU rules and points, and your own jumps "
        "(“What was my last jump?”, “How many falls this week?”)."
    ),
    "LLMUnavailable": "No language model is connected, so there is no written summary. The best matching source excerpt is shown.",
}

_NO_INDEX = (
    "The full knowledge-base search is not set up on this server yet (the search index "
    "has not been built). Instant answers still work: jump definitions, ISU marks, causes "
    "of common errors and their drills, warm-up, rest and training frequency."
)


def ask(question: str, k: int = 5, lang: str = "en") -> dict:
    """A short answer from the retrieved sources.

    Structured lookups first (deterministic, no LLM); then retrieval, and the
    LLM writes 2-4 sentences ONLY from the retrieved passages. Numbers and
    wording are validated against the sources. `lang` is accepted for API
    compatibility; the product is English only.
    """
    for _first in (_safety_lookup, _isu_marks_lookup, _personal_lookup):
        try:
            hit = _first(question)
        except Exception as _e:  # noqa: BLE001
            print(f"[coach-ask] {_first.__name__}: {type(_e).__name__}: {_e}", file=sys.stderr, flush=True)
            hit = None
        if hit:
            return hit
    isu = _isu_lookup(question)
    if isu:
        return isu
    for _structured in (
        _unsure_lookup,
        _about_lookup,
        _personal_data_lookup,
        _sourced_lookup,
        _scope_lookup,
        _app_lookup,
        _my_jump_lookup,
        _glossary_lookup,
        _science_lookup,
        _lutz_flip_lookup,
        _worth_lookup,
        _order_lookup,
        _compare_lookup,
        _jump_def_lookup,
        _office_lookup,
        _methodology_lookup,
        _rest_lookup,
        _error_fix_lookup,
        _drill_lookup,
    ):
        try:
            hit = _structured(question)
        except Exception as _e:  # noqa: BLE001
            print(
                f"[coach-ask] structured answer {_structured.__name__}: {type(_e).__name__}: {_e}",
                file=sys.stderr,
                flush=True,
            )
            hit = None
        if hit:
            return hit
    if not CORPUS.is_file():
        return {
            "answer": _NO_INDEX,
            "grounded": True,
            "structured": "no_index",
            "sources": [],
            "note": f"build it with: {_BUILD_HINT}",
        }
    # The embedding model is still loading (cold start): do not keep the
    # person waiting; search lexically (BM25) over the same corpus meanwhile.
    lexical_hits = None
    if embed._model is None and not _FALLBACK_READY.is_set():
        warm_fallback(background=True)
        if not _FALLBACK_READY.wait(timeout=min(_FALLBACK_WAIT_S, 2.0)):
            lexical_hits = _lexical_hits(question, k)
        if lexical_hits is None and not _FALLBACK_READY.is_set():
            return {
                "answer": (
                    "The full knowledge-base search is still starting up — ask again in a "
                    "minute. Instant answers work now: jump definitions, ISU marks, causes of "
                    "common errors and their drills, warm-up, rest and training frequency."
                ),
                "grounded": True,
                "structured": "warming",
                "sources": [],
            }
    if lexical_hits:
        hits = lexical_hits
    else:
        rows, emb = _load()
        q = _m().encode([f"query: {question}"[:400]], normalize_embeddings=True)
        sims = (emb @ q.T).ravel()
        order = np.argsort(-sims)[:k]
        hits = [{**rows[i], "score": round(float(sims[i]), 3)} for i in order]
    srcs = [{"source": h["source"], "url": h["url"], "score": h["score"]} for h in hits]
    messages = _MESSAGES

    def fallback(reason: str, *, grounded: bool = True) -> dict:
        source = hits[0] if hits else {}
        text = source.get("text", "")
        return {
            "answer": _tidy_excerpt(text) or messages["no_answer"],
            "sources": srcs,
            "grounded": grounded,
            "failure_kind": reason,
            "note": messages.get(reason, messages["excerpt"]),
        }

    # Passage numbers are NOT a source of numbers: the validator takes allowed
    # numbers from the passage texts, never from the "[1]".."[5]" markers.
    src_texts = [h["text"][:600] for h in hits]
    ctx = "\n\n".join(f"[{i + 1}] {t}" for i, t in enumerate(src_texts))
    words = set(re.findall(r"[\w']+", question.lower()))
    if words & set(_PERSONAL):  # a question about the user
        uc = _user_context()
        if uc:
            ctx = "[USER DATA]\n" + uc + "\n\n" + ctx
            src_texts.append(uc)  # the profile numbers are a source too
            srcs = [{"source": "your profile and analyses", "url": "", "score": 1.0}] + srcs
    try:
        from ..llm import complete_json
        from ..prompts import ANSWER_QUESTION, SYSTEM_GROUNDED

        js = complete_json(
            ANSWER_QUESTION.format(question=question, sources=ctx, lang="English")
            + "\nAnswer in 2-4 short sentences in plain words using ONLY facts from the sources "
            "(you may paraphrase and combine them). Copy numbers exactly. If the sources only "
            "partly cover the question, give the most useful practical guidance they DO support. "
            "Return not_stated only if no source is related to the question at all.",
            system=SYSTEM_GROUNDED,
            timeout=15,
        )
        ans = (js.get("answer") or "").strip()
        # Every number in the answer must occur in the sources.
        src_nums = set(re.findall(r"\d+(?:[.,]\d+)?", "\n".join(src_texts)))
        bad = [
            n for n in re.findall(r"\d+(?:[.,]\d+)?", ans) if n not in src_nums and n.replace(",", ".") not in src_nums
        ]
        if bad:
            return fallback("unverified_numbers", grounded=False)
        # "not_stated" is a contract word and must never be shown: a very short
        # answer that contains a marker is treated as "no answer".
        _norm = re.sub(r"[^\w\s]", " ", ans.lower().replace("_", " ")).strip()
        _markers = ("stated", "unknown", "n a", "none", "no data")
        if len(_norm) <= 40 and any(m in _norm for m in _markers):
            return {"answer": messages["no_answer"], "sources": srcs, "grounded": True, "no_answer": True}
        if ans:
            # Matching digits do not prove a claim (640 deg/s is not 640 seconds):
            # accept the verbatim source text, or a paraphrase whose content
            # words come from the sources.
            normalized = " ".join(ans.split())
            supported = any(normalized == " ".join(hit["text"].split()) for hit in hits)
            if supported:
                return {
                    "answer": _tidy_excerpt(ans),
                    "sources": srcs,
                    "grounded": True,
                    "verification_scope": "source_excerpt",
                }
            if _grounded_paraphrase(ans, src_texts):
                return {"answer": ans, "sources": srcs, "grounded": True, "verification_scope": "paraphrase"}
            return fallback("unsupported_claim", grounded=False)
        return fallback("empty_answer")
    except Exception as _e:  # noqa: BLE001
        # The reason of the failure must be visible, not hidden by a bare except.
        _kind = type(_e).__name__
        print(f"[coach-ask] LLM unavailable: {_kind}: {str(_e)[:200]}", file=sys.stderr, flush=True)
        return fallback(_kind)
