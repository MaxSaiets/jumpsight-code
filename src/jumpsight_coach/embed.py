"""Semantic index over the drills and causes of the knowledge base.

Used by pipeline P7. The index is cached in STATE_DIR/kb_cache/ and rebuilt
when the content of the knowledge base changes. It is never stored in git.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import yaml

from jumpsight_core.paths import KB_DIR, STATE_DIR

EMBED_MODEL = "intfloat/multilingual-e5-small"
EMBED_DIM = 384
CACHE_DIR = STATE_DIR / "kb_cache"
_CACHE = CACHE_DIR / "emb_cache.npz"
_model = None


def _m():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _kb_items() -> list[dict]:
    """Drills and causes as one list of searchable items."""
    items = []
    drills = yaml.safe_load((KB_DIR / "drills.yaml").read_text(encoding="utf-8"))
    for d in drills:
        items.append(
            {
                "type": "drill",
                **d,
                "_text": f"{d['name']}. targets: {', '.join(d['targets'])}. {' '.join(d.get('cues', []))}",
            }
        )
    causes = yaml.safe_load((KB_DIR / "causes.yaml").read_text(encoding="utf-8"))
    for code, blk in (causes or {}).items():
        for c in (blk or {}).get("causes", []):
            items.append({"type": "cause", "code": code, **c, "_text": f"problem {code}: {c['text']}"})
    return items


def _digest(items) -> str:
    return hashlib.md5(json.dumps([i["_text"] for i in items], ensure_ascii=False).encode()).hexdigest()


def build_index() -> tuple[list[dict], np.ndarray]:
    items = _kb_items()
    dig = _digest(items)
    if _CACHE.exists():
        z = np.load(_CACHE, allow_pickle=True)
        if str(z["digest"]) == dig:
            return items, z["emb"]
    emb = _m().encode([f"passage: {i['_text']}"[:800] for i in items], normalize_embeddings=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(_CACHE, emb=emb, digest=dig)
    return items, emb


def search(query: str, k: int = 10) -> list[dict]:
    items, emb = build_index()
    q = _m().encode([f"query: {query}"[:500]], normalize_embeddings=True)
    sims = (emb @ q.T).ravel()
    order = np.argsort(-sims)[:k]
    return [{**items[i], "_score": round(float(sims[i]), 3)} for i in order]
