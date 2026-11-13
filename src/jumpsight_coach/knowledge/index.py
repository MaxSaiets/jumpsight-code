"""Corpus build, embedding cache, index load and the warm-up of the fallback retrieval path."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request

import numpy as np

from .. import embed
from .corpus import _BUILD_HINT, CACHE_DIR, CORPUS, EMB, WIKI_EN, CorpusMissing, _chunk, _kb_rows, _on_topic, _wiki_text


def _m():
    return embed._m()


def _digest(rows) -> str:
    return hashlib.md5(json.dumps([r["text"][:60] for r in rows]).encode()).hexdigest()


def _embed(rows, force=False) -> np.ndarray:
    dig = _digest(rows)
    if EMB.exists() and not force:
        z = np.load(EMB, allow_pickle=True)
        if str(z["digest"]) == dig:
            return z["emb"]
    print(f"  embedding {len(rows)} passages...")
    emb = _m().encode(
        [f"passage: {r['text']}"[:600] for r in rows], normalize_embeddings=True, batch_size=64, show_progress_bar=False
    )
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(EMB, emb=emb, digest=dig)
    return emb


def _load() -> tuple[list[dict], np.ndarray]:
    if not CORPUS.is_file():
        raise CorpusMissing(f"knowledge corpus not built ({CORPUS}); run: {_BUILD_HINT}")
    rows = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line]
    return rows, _embed(rows)


def build() -> int:
    """Build the corpus and its embeddings into STATE_DIR/kb_cache/.

    Needs network access for Wikipedia and a one-time download of the
    embedding model."""
    rows: list[dict] = []
    for t in WIKI_EN:
        try:
            txt = _wiki_text(t)
        except Exception as ex:
            print(f"  wiki {t}: {ex}")
            continue
        kept = 0
        chunks = _chunk(txt)[:40]
        for ch in chunks:
            if not _on_topic(ch):
                continue
            kept += 1
            rows.append(
                {
                    "text": ch,
                    "lang": "en",
                    "source": f"Wikipedia (en): {t}",
                    "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_")),
                    "kind": "wiki",
                }
            )
        print(f"  wiki {t}: +{kept} ({len(chunks) - kept} off-topic dropped)")
    rows += _kb_rows()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print(f"{CORPUS}: {len(rows)} passages")
    _embed(rows, force=True)
    return len(rows)


_FALLBACK_READY = __import__("threading").Event()
_FALLBACK_LOCK = __import__("threading").Lock()
_FALLBACK_WAIT_S = float(os.environ.get("JS_FALLBACK_WAIT_S", "8"))


def warm_fallback(background: bool = False) -> None:
    """Bring up what an answer outside the structured lookups needs: the
    embedding model, the embedding cache and the LLM client."""

    def go():
        if not _FALLBACK_LOCK.acquire(blocking=False):
            return
        try:
            _load()
            _m().encode(["query: warm"], normalize_embeddings=True)
            try:
                from ..llm import _openai, provider

                if provider() == "openai":
                    _openai().chat  # noqa: B018 (attribute access imports the client resources)
            except Exception:  # noqa: BLE001
                pass
            _FALLBACK_READY.set()
        except CorpusMissing:
            print(f"[knowledge] corpus not built; run: {_BUILD_HINT}", flush=True)
        finally:
            _FALLBACK_LOCK.release()

    if background:
        __import__("threading").Thread(target=go, daemon=True).start()
    else:
        go()
