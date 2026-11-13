"""Stage 3 of the ingestion: one card per library drill (what for, when, conditions).

    python -m jumpsight_coach.ingest.build_cards --motion FILE --transcripts FILE [--drills FILE] [--out FILE]

Input:  library_motion.json (stage 2) and a transcripts JSON, both keyed by
        drill id, plus a drills YAML (default: the knowledge base drills.yaml)
        and kb/causes.yaml.
Output: STATE_DIR/lesson_library/library_cards.yaml (or --out). Every card
        merges independent channels without an LLM, each traceable to its
        source: measured motion, narration, the drill targets (when to give it,
        from the causes) and the negative knowledge (contraindications).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from jumpsight_core.paths import KB_DIR, LESSON_LIBRARY_DIR


def build(drills_path: Path, motion_path: Path, transcripts_path: Path, out: Path) -> int:
    drills = yaml.safe_load(drills_path.read_text(encoding="utf-8"))
    causes = yaml.safe_load((KB_DIR / "causes.yaml").read_text(encoding="utf-8"))
    motion = json.loads(motion_path.read_text(encoding="utf-8"))
    trans = json.loads(transcripts_path.read_text(encoding="utf-8"))
    negatives = [d for d in drills if d.get("kind") == "do_not_recommend"]

    cards = []
    for d in drills:
        if d["id"] not in motion:
            continue
        mo = motion.get(d["id"]) or {}
        tr = trans.get(d["id"]) or []
        when = []
        for t in d.get("targets", []):
            for c in (causes.get(t) or {}).get("causes", [])[:1]:
                vis = c.get("visible_in", "")
                when.append(
                    f"[{t}] {c['text']}" + (f" (visible as: {vis})" if vis and "not measured" not in vis else "")
                )
        contra = [
            f"Do NOT combine with: {n['name']} - {n['cues'][0][:80]}"
            for n in negatives
            if set(n.get("targets", [])) & set(d.get("targets", []))
        ]
        lvl = d.get("level", 1)
        conditions = [f"from level {lvl} ({'beginner' if lvl <= 1 else 'intermediate' if lvl <= 2 else 'advanced'})"]
        if d.get("requires_supervision"):
            conditions.append("ONLY under a coach's supervision")
        if d.get("kind") == "off_ice":
            conditions.append("off-ice: check the transfer to the ice separately (Bruening 2006)")
        if d.get("progression"):
            conditions.append(f"part of the ladder {d['progression']} - steps in order")
        cards.append(
            {
                "drill_id": d["id"],
                "name": d["name"],
                "what_happens": mo.get("motion_text", "-"),
                "duration_s": mo.get("dur_s"),
                "for_what": d.get("targets", []),
                "when_to_give": when,
                "conditions": conditions,
                "how": d.get("cues", []),
                "narration_first_lines": [row["text"] for row in tr[:2]],
                "dosage": d.get("dosage", ""),
                "exit_criteria": d.get("exit_criteria", "3 clean performances in a row (the default gate)"),
                "contraindications": contra,
                "evidence": d.get("evidence", "B"),
                "evidence_sources": d.get("evidence_sources", ["library"]),
            }
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cards, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"{out}: {len(cards)} cards")
    return len(cards)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drills", default=str(KB_DIR / "drills.yaml"))
    ap.add_argument("--motion", required=True)
    ap.add_argument("--transcripts", required=True)
    ap.add_argument("--out", default=str(LESSON_LIBRARY_DIR / "library_cards.yaml"))
    a = ap.parse_args()
    build(Path(a.drills), Path(a.motion), Path(a.transcripts), Path(a.out))
