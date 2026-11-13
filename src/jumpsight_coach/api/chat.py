"""Chat and knowledge-base routes: /ask, drill library, KB gaps, LLM health."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core import load_kb
from .mascot import _mascot_file_for

router = APIRouter()


class AskIn(BaseModel):
    question: str
    lang: str = "en"


@router.get("/kb/gaps")
def kb_gaps(lang: str = "en") -> dict:
    """Where the database is empty and what can close the gap, without inventing drills.

    The review queue is ranked by the gaps that progress runs into, and the gaps that no candidate covers at
    all are named separately: those need new filming, and saying so is more honest than staying silent.
    """
    from ..kb_gaps import gaps

    return gaps()


@router.get("/llm_health")
def llm_health(request: Request, force: int = 0) -> dict:
    """Which LLM provider is active and whether it is alive.

    The answer is cached: each call is a real request with the provider key, and the diagnostics screen is opened more often than the provider changes state. `?force=1` deliberately bypasses the cache.
    """
    # The frontend does not use this route: in production it is reachable only with the admin token.
    from ..llm import health, is_prod

    if is_prod():
        import os as _os

        _tok = _os.environ.get("JS_COACH_TOKEN", "")
        if not _tok or request.headers.get("x-coach-token", "") != _tok:
            raise HTTPException(status_code=404)
    return health(force=bool(force))


@router.post("/ask")
def ask_kb(inp: AskIn) -> dict:
    """RAG chat: a short answer assembled ONLY from the sources found."""
    from ..knowledge import ask

    return ask(inp.question, lang=inp.lang)


@router.get("/kb/list")
def kb_list(lang: str = "en") -> list[dict]:
    """Drill library."""
    drills, _ = load_kb()
    out = []
    for d in drills:
        out.append(
            {
                "id": d["id"],
                "name": d["name"],
                "kind": d.get("kind"),
                "level": d.get("level"),
                "targets": d.get("targets", []),
                "evidence": d.get("evidence", "B"),
                "has_demo": _mascot_file_for(d) is not None,
                "url": d.get("url", ""),
                "dosage": d.get("dosage", ""),
                "steps": d.get("steps", [])[:6],
                "cues": d.get("cues", [])[:3],
            }
        )
    return out
