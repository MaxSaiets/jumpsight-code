"""Stage 6 of the ingestion: mine drills from timed transcript chunks.

    python -m jumpsight_coach.ingest.mine_drills [--chunks FILE] [--out FILE]

Input:  library_chunks.jsonl from `ingest.transcript_chunks`.
Output: STATE_DIR/lesson_library/library_mined.yaml and library_mined_rejected.yaml
        (or --out and its sibling). Needs OPENAI_API_KEY.

Extract -> VERIFY -> dedup -> provenance:
  - the LLM extracts steps (not just cues), structured dosage, mistakes, a
    success gate and a level hint; "not_stated" is a legal value and numbers
    are NEVER guessed;
  - the LLM does NOT give a timecode: it gives a VERBATIM quote and the code
    recovers t0 by matching the quote against the timed segments; a quote that
    cannot be found sends the entry to the rejected file with the reason;
  - verification: a separate role sees only the claim and a transcript window;
    unsupported -> rejected, partial -> `review: true`, `verification: partial`;
  - dedup: within a video by normalised name; across videos by a double
    embedding threshold (>=0.88 AND a gap >=0.02);
  - provenance on every record: video id, url + t, quote, prompt version.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from jumpsight_core.paths import LESSON_LIBRARY_DIR

from .. import llm
from ..embed import EMBED_MODEL
from .transcript_chunks import load_corpus

PROMPT_VERSION = 3
CODES = (
    "under_rotation two_foot_landing landing_stability low_height "
    "late_check_out axis_tilt rotation_power air_position fall "
    "stiff_landing_knee basics_rotation spin_flexibility "
    "spin_position balance_control"
)

_EXTRACT = """From a figure skating lesson transcript extract the DRILLS.
Return STRICTLY JSON:
{{"entries":[{{"drill_name":"...","problems":["code",...],
 "when_symptom":"when to give it, or not_stated",
 "why":"why it helps, or not_stated",
 "steps":["step 1","step 2"],
 "dosage_text":"VERBATIM as said (3x10, 2 minutes) or not_stated",
 "mistakes":[{{"mistake":"...","fix":"... or null"}}],
 "success":"success criterion as said, or not_stated",
 "level_hint":"beginner|intermediate|advanced|not_stated",
 "quote":"a verbatim fragment of 5-15 words FROM THE TRANSCRIPT proving the drill exists"}}]}}

RULES (a violation gets the entry rejected):
- problem codes ONLY from: {codes}
- not_stated is a LEGAL answer; DO NOT INVENT NUMBERS - verbatim only
- quote is a copy of words from the transcript, NOT a paraphrase
- steps are actions in order, in the source's words
- at most 6 entries, real drills only (not chat)

EXAMPLE of one entry:
{{"drill_name":"Landing position hops","problems":["landing_stability","two_foot_landing"],
 "when_symptom":"unstable landing on one foot","why":"builds balance on the landing leg",
 "steps":["stand on the landing leg","hop while holding the exit position"],
 "dosage_text":"not_stated","mistakes":[{{"mistake":"free leg drops","fix":"keep it at height"}}],
 "success":"not_stated","level_hint":"beginner",
 "quote":"stand on one leg in a strong landing position"}}

TRANSCRIPT ({title}):
{text}"""

_VERIFY = """You are a fact checker. You are given CLAIMS about drills and a WINDOW
of a lesson transcript. For EACH claim give a verdict:
supported (directly confirmed) / partial (partly) / unsupported (absent).
Return STRICTLY JSON: {{"verdicts":[{{"n":1,"verdict":"supported"}},...]}}

CLAIMS:
{claims}

TRANSCRIPT WINDOW:
{window}"""


def _norm_name(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", s.lower())
    stop = {"the", "a", "drill", "exercise", "and", "with", "for"}
    return " ".join(w for w in re.findall(r"[a-z]+", s) if w not in stop and len(w) > 2)


def _find_quote(quote: str, segs: list[dict]) -> tuple[int, float] | None:
    """Recover t0 by code: look for the quote in the timed segments."""
    qn = " ".join(quote.lower().split())
    best, best_r = None, 0.0
    for s in segs:
        txt = s["text"].lower()
        if qn[:40] in txt:
            return int(s["t0"]), 1.0
        r = difflib.SequenceMatcher(None, qn[:80], txt[:400]).ratio()
        if r > best_r:
            best_r, best = r, int(s["t0"])
    if best_r >= 0.55:  # ASR noise: an empirical threshold, below it we refuse
        return best, best_r
    return None


def mine(chunks_path: Path, out_path: Path) -> None:
    corpus = load_corpus(chunks_path)
    by_vid = defaultdict(list)
    for c in corpus:
        by_vid[c["video_id"]].append(c)
    accepted, rejected = [], []
    for vid, segs in by_vid.items():
        segs.sort(key=lambda c: c["t0"])
        text = "\n".join(f"[{int(c['t0'])}s] {c['text']}" for c in segs)[:9000]
        title = segs[0]["title"]
        try:
            js = llm.complete_json(_EXTRACT.format(codes=CODES, title=title, text=text))
        except Exception as ex:
            print(f"  {title[:40]}: extraction failed: {str(ex)[:80]}")
            continue
        entries = []
        for e in js.get("entries", []):
            probs = [p for p in e.get("problems", []) if p in CODES.split()]
            if not e.get("drill_name") or not probs or not e.get("quote"):
                rejected.append({"entry": e, "video": vid, "reason": "no name/codes/quote"})
                continue
            loc = _find_quote(e["quote"], segs)
            if not loc:
                rejected.append(
                    {"entry": e, "video": vid, "reason": "quote not found in the transcript (possible hallucination)"}
                )
                continue
            t0, sim = loc
            e["_t0"], e["_sim"], e["_vid"], e["_title"] = t0, sim, vid, title
            e["problems"] = probs
            entries.append(e)
        entries = _verify(entries, segs, rejected)
        accepted += entries
        print(f"  {title[:44]}: +{len(entries)} (rejected {sum(1 for r in rejected if r['video'] == vid)})")
    final = _dedup(accepted)
    out = []
    for e in final:
        out.append(
            {
                "id": f"mined_{e['_vid']}_{e['_t0']}",
                "name": e["drill_name"],
                "kind": "off_ice",
                "targets": e["problems"],
                "when": "" if e.get("when_symptom") == "not_stated" else e.get("when_symptom", ""),
                "why": "" if e.get("why") == "not_stated" else e.get("why", ""),
                "steps": e.get("steps", []),
                "cues": e.get("steps", [])[:3],
                "dosage": "" if e.get("dosage_text") == "not_stated" else e.get("dosage_text", ""),
                "mistakes_to_avoid": [m for m in e.get("mistakes", []) if m.get("mistake")],
                "success": "" if e.get("success") == "not_stated" else e.get("success", ""),
                "level_hint": e.get("level_hint", "not_stated"),
                "source": "transcript",
                "url": f"https://www.youtube.com/watch?v={e['_vid']}&t={e['_t0']}s",
                "review": True,
                # fail-closed: a missing field means UNVERIFIED
                "verification": e.get("_verification", "unverified"),
                "provenance": [
                    {
                        "video_id": e["_vid"],
                        "t0": e["_t0"],
                        "quote": e["quote"],
                        "quote_match": round(e["_sim"], 2),
                        "prompt_version": PROMPT_VERSION,
                    }
                ],
            }
        )
    # on-ice heuristic: edge/spin/ice words in the text -> on_ice
    onice_kw = ("edge", "spin", "3 turn", "wall", "board", "ice")
    for e in out:
        txt = (e["name"] + " " + e["why"] + " " + " ".join(e["steps"])).lower()
        if any(k in txt for k in onice_kw):
            e["kind"] = "on_ice"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8")
    rej_path = out_path.with_name(out_path.stem + "_rejected.yaml")
    rej_path.write_text(yaml.safe_dump(rejected, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"{out_path}: {len(out)} (after dedup), rejected: {len(rejected)} -> {rej_path}")


def _verify(entries: list[dict], segs: list[dict], rejected: list[dict]) -> list[dict]:
    if not entries:
        return entries
    # Claims are numbered 1..2N so that the verdict keys n = 2i-1 and 2i match.
    claims, windows = [], []
    for i, e in enumerate(entries, 1):
        claims.append(f'{2 * i - 1}. The lesson contains the drill "{e["drill_name"]}"')
        claims.append(f"{2 * i}. It addresses the problem: {', '.join(e['problems'])}")
        t0 = e["_t0"]
        win = " ".join(s["text"] for s in segs if abs(s["t0"] - t0) <= 90)
        windows.append(win[:1200])
    try:
        js = llm.complete_json(_VERIFY.format(claims="\n".join(claims), window="\n---\n".join(dict.fromkeys(windows))))
        # the key may arrive as a string - coerce to int
        verd = {}
        for v in js.get("verdicts", []):
            try:
                verd[int(v.get("n"))] = v.get("verdict", "unverified")
            except (TypeError, ValueError):
                continue
    except Exception as _e:  # noqa: BLE001
        # three states must differ: verified-and-unsupported, the verifier did
        # not answer, the verification was not run
        print(f"[mine_drills] verifier failed: {type(_e).__name__}: {str(_e)[:160]}", file=sys.stderr, flush=True)
        for e in entries:
            e["_verification"] = "verifier_failed"
        return entries
    kept = []
    for i, e in enumerate(entries, 1):
        va = verd.get(2 * i - 1, "unverified")
        vb = verd.get(2 * i, "unverified")
        if va == "unsupported":
            rejected.append(
                {
                    "entry": {"drill_name": e["drill_name"]},
                    "video": e["_vid"],
                    "reason": "verification: the existence of the drill is not supported by the transcript window",
                }
            )
            continue
        e["_verification"] = (
            "supported" if va == vb == "supported" else "unverified" if "unverified" in (va, vb) else "partial"
        )
        kept.append(e)
    return kept


def _dedup(entries: list[dict]) -> list[dict]:
    # 1) within a video: the same normalised name -> keep the one with a dosage
    by_key = {}
    for e in entries:
        k = (e["_vid"], _norm_name(e["drill_name"]))
        cur = by_key.get(k)
        if cur is None or (cur.get("dosage_text") == "not_stated" and e.get("dosage_text") != "not_stated"):
            by_key[k] = e
    entries = list(by_key.values())
    # 2) across videos: a double embedding threshold
    if len(entries) < 2:
        return entries
    try:
        from sentence_transformers import SentenceTransformer

        m = SentenceTransformer(EMBED_MODEL)
        texts = [f"passage: {e['drill_name']} {' '.join(e.get('steps', []))}"[:400] for e in entries]
        E = m.encode(texts, normalize_embeddings=True)
        S = E @ E.T
        drop = set()
        for i in range(len(entries)):
            if i in drop:
                continue
            row = sorted(((float(S[i, j]), j) for j in range(len(entries)) if j != i and j not in drop), reverse=True)
            if not row:
                continue
            top, j = row[0]
            second = row[1][0] if len(row) > 1 else 0.0
            if top >= 0.88 and top - second >= 0.02 and entries[i]["_vid"] != entries[j]["_vid"]:
                # merge: the goals are united, the record with a dosage stays
                a, b = entries[i], entries[j]
                keep, other = (a, b) if a.get("dosage_text") != "not_stated" else (b, a)
                keep["problems"] = sorted(set(keep["problems"]) | set(other["problems"]))
                drop.add(entries.index(other))
        return [e for k, e in enumerate(entries) if k not in drop]
    except Exception:
        return entries


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chunks", default=str(LESSON_LIBRARY_DIR / "library_chunks.jsonl"))
    ap.add_argument("--out", default=str(LESSON_LIBRARY_DIR / "library_mined.yaml"))
    a = ap.parse_args()
    mine(Path(a.chunks), Path(a.out))
