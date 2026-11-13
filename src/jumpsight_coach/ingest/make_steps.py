"""Stage 4 of the ingestion: instruction steps for drills that have none.

    python -m jumpsight_coach.ingest.make_steps [--drills FILE] [--transcripts FILE] [--out FILE]

Input:  a drills YAML (default: the knowledge base drills.yaml); optionally a
        transcripts JSON {"<drill id>": [{"t": sec, "text": line}, ...]} (the
        output of `jumpsight_mascot.voice.narrate.transcribe_lesson`, keyed by
        drill id).
Output: a copy of the drills YAML with `steps` added, written to --out
        (default STATE_DIR/lesson_library/library_drills.yaml); the input is
        never overwritten.

The LLM only structures existing text into 2-4 steps. It may not add actions
or numbers; every step must share content words with the source, otherwise the
drill stays without steps: empty is better than invented.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

from jumpsight_core.paths import KB_DIR, LESSON_LIBRARY_DIR

from .. import llm
from ..prompts import MAKE_STEPS, SYSTEM_GROUNDED

_STOP = {
    "the",
    "and",
    "with",
    "your",
    "you",
    "then",
    "make",
    "let's",
    "for",
    "this",
    "that",
    "same",
    "time",
    "try",
    "can",
    "will",
    "just",
    "into",
}


def _key_words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in _STOP}


def main(drills_path: Path, transcripts: Path | None, out_path: Path) -> None:
    drills = yaml.safe_load(drills_path.read_text(encoding="utf-8"))
    tr = json.loads(transcripts.read_text(encoding="utf-8")) if transcripts else {}
    done = skipped = rejected = 0
    for d in drills:
        if d.get("steps") or d.get("kind") == "do_not_recommend":
            continue
        narration = " ".join(row["text"] for row in tr.get(d["id"], []))
        source = (narration or " ".join(d.get("cues", []))).strip()
        if len(source) < 25:
            skipped += 1
            continue
        try:
            js = llm.complete_json(
                MAKE_STEPS.format(name=d["name"], source=source[:1500], lang="English"), system=SYSTEM_GROUNDED
            )
            steps = [s.strip() for s in js.get("steps", []) if s.strip()][:4]
        except Exception as ex:
            print(f"  {d['id']}: failed ({str(ex)[:50]})")
            skipped += 1
            continue
        if not steps:
            skipped += 1
            continue
        # validation: only numbers that exist in the source
        src_nums = set(re.findall(r"\d+", source))
        bad_num = [n for s in steps for n in re.findall(r"\d+", s) if n not in src_nums]
        if bad_num:
            print(f"  {d['id']}: REJECTED - invented numbers {bad_num}")
            rejected += 1
            continue
        # content words: each step must lean on the source
        src_words = _key_words(source)
        steps = [s for s in steps if _key_words(s) & src_words]
        if not steps:
            rejected += 1
            continue
        d["steps"] = steps
        d["steps_source"] = "narration" if narration else "drill cues"
        done += 1
        print(f"  {d['id']}: {steps[0][:60]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(drills, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"\nsteps added: {done}, skipped: {skipped}, rejected for invented numbers: {rejected}")
    print(f"written: {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drills", default=str(KB_DIR / "drills.yaml"))
    ap.add_argument("--transcripts", default=None)
    ap.add_argument("--out", default=str(LESSON_LIBRARY_DIR / "library_drills.yaml"))
    a = ap.parse_args()
    main(Path(a.drills), Path(a.transcripts) if a.transcripts else None, Path(a.out))
