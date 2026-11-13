"""Coach chat: numbers in the answer must be in the sources.

The validator must not collect the allowed numbers by regex over the whole context, which is built as '[1] text', '[2] text': the passage markers would put the digits 1-5 into the allowed set, and in figure skating 1-4 are revolution counts. On a context without a single digit, 'a triple Lutz is 3 revolutions', 'hold 2 seconds, do 5 sets' and 'double jumps spin 4 revolutions per second' must all be rejected.

The models do not load here: both the encoder and the LLM are substituted (the multilingual-e5-small weight is not cached on this machine; the test would pull ~0.5 GB).
"""

from __future__ import annotations

import numpy as np


class _Encoder:
    def encode(self, _texts, **_kw):
        return np.array([[1.0, 0.0]], dtype=np.float32)


def _stub_sources(monkeypatch, texts):
    from jumpsight_coach import knowledge

    rows = [{"text": t, "source": f"source {i}", "url": ""} for i, t in enumerate(texts)]
    emb = np.tile(np.array([[1.0, 0.0]], dtype=np.float32), (len(rows), 1))
    monkeypatch.setattr(knowledge, "CORPUS", __import__("pathlib").Path(__file__))
    monkeypatch.setattr(knowledge.embed, "_model", object())
    monkeypatch.setattr(knowledge, "_load", lambda: (rows, emb))
    monkeypatch.setattr(knowledge, "_m", lambda: _Encoder())
    monkeypatch.setattr(knowledge, "_isu_lookup", lambda *a, **k: None)
    return knowledge


def _stub_llm(monkeypatch, answer=None, exc=None):
    from jumpsight_coach import llm

    def _fake(*_a, **_k):
        if exc is not None:
            raise exc
        return {"answer": answer}

    monkeypatch.setattr(llm, "complete_json", _fake)


def test_invented_rotation_counts_are_caught(monkeypatch):
    k = _stub_sources(
        monkeypatch,
        [
            "The Lutz enters from the outside edge of the left foot and takes off with the right toe pick.",
            "The entry edge tells a Lutz from a flip; the coach looks at the track.",
        ],
    )
    _stub_llm(monkeypatch, "A triple Lutz is 3 revolutions, hold 2 seconds, 5 sets.")
    r = k.ask("what does the entry edge mean", lang="en")
    assert r["grounded"] is False, r
    assert "not found in the sources" in (r.get("note") or "")


def test_exact_source_excerpt_passes(monkeypatch):
    k = _stub_sources(
        monkeypatch,
        [
            "Rotation speed in triples reaches 640 degrees per second.",
            "Flight time in doubles is about 0.55 seconds.",
        ],
    )
    _stub_llm(monkeypatch, "Rotation speed in triples reaches 640 degrees per second.")
    r = k.ask("what does the entry edge mean", lang="en")
    assert r["grounded"] is True, r
    assert r["verification_scope"] == "source_excerpt", r


def test_unsupported_non_numeric_claim_is_rejected(monkeypatch):
    k = _stub_sources(monkeypatch, ["Keep the landing controlled."])
    _stub_llm(monkeypatch, "The moon is made of cheese.")
    r = k.ask("Explain landing", lang="en")
    assert r["grounded"] is False
    assert r["failure_kind"] == "unsupported_claim"
    assert "cheese" not in r["answer"]


def test_source_number_cannot_be_reassigned_to_other_units(monkeypatch):
    k = _stub_sources(monkeypatch, ["Rotation speed can reach 640 degrees per second."])
    _stub_llm(monkeypatch, "Hold your landing for 640 seconds.")
    r = k.ask("Explain landing", lang="en")
    assert r["grounded"] is False
    assert r["failure_kind"] == "unsupported_claim"
    assert "Hold your landing" not in r["answer"]


def test_empty_answer_does_not_blame_the_provider(monkeypatch):
    k = _stub_sources(monkeypatch, ["A text without digits about the entry edge."])
    _stub_llm(monkeypatch, "")
    r = k.ask("what does the entry edge mean", lang="en")
    assert r.get("failure_kind") == "empty_answer", r
    assert "unavailable" not in (r.get("note") or ""), r


def test_provider_failure_is_named(monkeypatch):
    k = _stub_sources(monkeypatch, ["A text without digits about the entry edge."])
    _stub_llm(monkeypatch, exc=TimeoutError("timeout"))
    r = k.ask("what does the entry edge mean", lang="en")
    assert r.get("failure_kind") == "TimeoutError", r
