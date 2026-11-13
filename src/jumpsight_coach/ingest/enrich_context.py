"""Stage 5 of the ingestion: enrich drills through the theory (context-aware).

    python -m jumpsight_coach.ingest.enrich_context --motion FILE --transcripts FILE [--drills FILE] [--out FILE]

A video shows HOW to do a drill, not FOR WHOM, WHEN and WHICH errors it fixes.
Asking an LLM to guess gives plausible inventions, so the order is theory first:
  1) facts about the drill (no LLM): cues, narration, measured motion;
  2) theory retrieval: semantic search over the knowledge corpus
     (needs the corpus built by `python -m jumpsight_coach.knowledge build`);
  3) generation in a narrow frame: the LLM fills a schema from these facts and
     this theory only; every field must cite a fragment or say "not_stated";
  4) validation by code: error codes in the taxonomy, levels in the enum,
     citations among the supplied fragments; a failing field is dropped;
  5) review: every record is `review: true` with the fragments it used.

Input:  motion and transcripts JSON keyed by drill id, and a drills YAML.
Output: STATE_DIR/lesson_library/library_context.yaml (or --out).
Needs OPENAI_API_KEY.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from jumpsight_core.paths import KB_DIR, LESSON_LIBRARY_DIR

from .. import llm
from .mine_drills import CODES

_PROMPT = """You are a figure skating training methodologist. Fill in the card of
a training drill. Rely ONLY on the supplied FACTS ABOUT THE DRILL and THEORY.
If the theory gives no grounds, write "not_stated". DO NOT INVENT.

Return STRICTLY JSON:
{{"for_whom":"level and who it suits, or not_stated",
 "when_in_session":"warmup|specific_warmup|main|volume|cooldown|not_stated",
 "use_case":"at which moment of preparation to give it (short) or not_stated",
 "fixes_errors":["codes from the taxonomy"],
 "prerequisites":["what to be able to do BEFORE this, in words"],
 "why_it_works":"mechanism: why the drill fixes these errors, or not_stated",
 "cite":[numbers of the theory fragments you rely on]}}

Error taxonomy (ONLY these codes): {codes}

FACTS ABOUT THE DRILL "{name}":
- coach cues: {cues}
- narration (transcript): {narration}
- MEASURED by skeleton: {motion}
- type: {kind}, duration {dur} s

THEORY (numbered fragments from the knowledge base):
{theory}"""


def _theory_for(query: str, k: int = 6) -> list[dict]:
    import numpy as np

    from ..knowledge import _load, _m

    rows, emb = _load()
    q = _m().encode([f"query: {query}"[:400]], normalize_embeddings=True)
    sims = (emb @ q.T).ravel()
    order = np.argsort(-sims)[:k]
    return [
        {"n": i + 1, "text": rows[j]["text"][:420], "source": rows[j]["source"], "url": rows[j].get("url", "")}
        for i, j in enumerate(order)
    ]


def enrich(drills_path: Path, motion_path: Path, transcripts_path: Path, out_path: Path) -> int:
    drills = yaml.safe_load(drills_path.read_text(encoding="utf-8"))
    motion = json.loads(motion_path.read_text(encoding="utf-8"))
    trans = json.loads(transcripts_path.read_text(encoding="utf-8"))
    codes = set(CODES.split())
    out = []
    for d in drills:
        if d["id"] not in motion:
            continue
        mo = motion.get(d["id"]) or {}
        narration = " ".join(row["text"] for row in (trans.get(d["id"]) or []))[:900]
        # retrieval on THREE sub-queries: the drill itself + session structure
        # + levels (otherwise the methodology fields stay not_stated)
        base_q = f"{d['name']} {' '.join(d.get('cues', []))}"
        theory = _theory_for(base_q, k=4)
        for extra in (
            "methodology session block warm-up main volume cool-down",
            "level beginner intermediate advanced who it suits",
        ):
            for t in _theory_for(extra, k=2):
                if t["text"] not in {x["text"] for x in theory}:
                    theory.append(t)
        for i, t in enumerate(theory, 1):
            t["n"] = i
        prompt = _PROMPT.format(
            codes=CODES,
            name=d["name"],
            cues="; ".join(d.get("cues", []))[:300],
            narration=narration or "none",
            motion=mo.get("motion_text", "none"),
            kind=d.get("kind", "?"),
            dur=mo.get("dur_s", "?"),
            theory="\n".join(f"[{t['n']}] {t['text']}" for t in theory),
        )
        try:
            js = llm.complete_json(prompt)
        except Exception as ex:
            print(f"  {d['id']}: failed ({str(ex)[:60]})")
            continue
        # --- validation by code ---
        fixes = [c for c in js.get("fixes_errors", []) if c in codes]
        cites = [c for c in js.get("cite", []) if isinstance(c, int) and 1 <= c <= len(theory)]
        when = js.get("when_in_session", "not_stated")
        if when not in ("warmup", "specific_warmup", "main", "volume", "cooldown", "not_stated"):
            when = "not_stated"
        rec = {
            "drill_id": d["id"],
            "name": d["name"],
            "for_whom": js.get("for_whom", "not_stated"),
            "when_in_session": when,
            "use_case": js.get("use_case", "not_stated"),
            "fixes_errors": fixes,
            "prerequisites_text": [str(x)[:120] for x in js.get("prerequisites", [])][:4],
            "why_it_works": js.get("why_it_works", "not_stated"),
            "review": True,
            "grounded_in": [{"n": t["n"], "source": t["source"], "url": t["url"]} for t in theory if t["n"] in cites]
            or [{"n": t["n"], "source": t["source"], "url": t["url"]} for t in theory[:2]],
            "no_citation": not cites,
        }
        out.append(rec)
        print(f"  {d['id']}: {when}, errors={fixes or '-'}, citations={len(cites)}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8")
    nc = sum(1 for r in out if r["no_citation"])
    print(f"{out_path}: {len(out)} cards (without theory citations: {nc} - review first)")
    return len(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drills", default=str(KB_DIR / "drills.yaml"))
    ap.add_argument("--motion", required=True)
    ap.add_argument("--transcripts", required=True)
    ap.add_argument("--out", default=str(LESSON_LIBRARY_DIR / "library_context.yaml"))
    a = ap.parse_args()
    enrich(Path(a.drills), Path(a.motion), Path(a.transcripts), Path(a.out))
