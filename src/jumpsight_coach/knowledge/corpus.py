"""Corpus sources: knowledge-base rows, Wikipedia pages, chunking and the cache paths."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

import yaml

from jumpsight_core.paths import KB_DIR, STATE_DIR

KB = KB_DIR
CACHE_DIR = STATE_DIR / "kb_cache"
CORPUS = CACHE_DIR / "knowledge_corpus.jsonl"
EMB = CACHE_DIR / "knowledge_emb.npz"


WIKI_EN = [
    "Figure skating jumps",
    "Axel jump",
    "Lutz jump",
    "Flip jump",
    "Loop jump",
    "Salchow jump",
    "Toe loop jump",
    "Figure skating spins",
    "ISU Judging System",
    "Single skating",
    "Figure skate",
]
_BUILD_HINT = "python -m jumpsight_coach.knowledge build"


class CorpusMissing(RuntimeError):
    """The corpus has not been built on this machine."""


def _wiki_text(title: str) -> str:
    import time

    url = (
        "https://en.wikipedia.org/w/api.php?action=query&prop=extracts"
        "&explaintext=1&format=json&redirects=1&titles=" + urllib.parse.quote(title)
    )
    req = urllib.request.Request(url, headers={"User-Agent": "jumpsight-kb/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:  # rate limit -> back off
                time.sleep(5 * (attempt + 1))
                continue
            raise
    time.sleep(1.2)  # polite pause between requests
    pages = d.get("query", {}).get("pages", {})
    for pg in pages.values():
        return pg.get("extract", "") or ""
    return ""


# Pages with ambiguous titles pull in unrelated articles; a Wikipedia chunk
# is kept only if it mentions skating.
_TOPIC = [
    "skat",
    "jump",
    "spin",
    "rotat",
    "blade",
    "edge",
    "ice",
    "landing",
    "takeoff",
    "axel",
    "lutz",
    "flip",
    "salchow",
    "toe",
    "loop",
    "rink",
    "judge",
    "program",
    "element",
    "toepick",
]


def _on_topic(text: str) -> bool:
    t = text.lower()
    return sum(1 for w in _TOPIC if w in t) >= 2


def _chunk(text: str, words: int = 90) -> list[str]:
    out, buf = [], []
    for w in text.split():
        buf.append(w)
        if len(buf) >= words:
            out.append(" ".join(buf))
            buf = []
    if len(buf) > 20:
        out.append(" ".join(buf))
    return out


def _kb_rows() -> list[dict]:
    rows: list[dict] = []
    for d in yaml.safe_load((KB / "drills.yaml").read_text(encoding="utf-8")):
        if d.get("kind") == "do_not_recommend":
            text = f"Do NOT: {d['name']}. {' '.join(d.get('cues', []))}"
        else:
            steps = " ".join(d.get("steps") or [])
            text = (
                f"Drill: {d['name']}. Works on: "
                f"{', '.join(t.replace('_', ' ') for t in d['targets'])}. "
                f"{' '.join(d.get('cues', []))}. {steps} Dosage: {d.get('dosage', '')}."
            )
        rows.append(
            {
                "text": text,
                "lang": "en",
                "source": f"KB drill [{d.get('evidence', 'B')}]",
                "url": d.get("url", ""),
                "kind": "drill",
            }
        )
    causes = yaml.safe_load((KB / "causes.yaml").read_text(encoding="utf-8"))
    for code, blk in causes.items():
        for c in (blk or {}).get("causes", []):
            rows.append(
                {
                    "text": f"Common cause of {code.replace('_', ' ')}: {c['text']} (source: {c.get('source', '')})",
                    "lang": "en",
                    "source": f"KB causes [{c.get('evidence', 'B')}]",
                    "url": "",
                    "kind": "cause",
                }
            )
    sci = yaml.safe_load((KB / "science.yaml").read_text(encoding="utf-8"))
    for f in sci.get("facts", []):
        m = re.search(r"https?://\S+", " ".join(f.get("sources") or []))
        rows.append(
            {
                "text": "Research: " + " ".join(f["text"].split()),
                "lang": "en",
                "source": "KB science [A]",
                "url": m.group(0) if m else "",
                "kind": "science",
            }
        )
    n = sci.get("norms", {}).get("rotation_speed_deg_s", {})
    if n:
        rows.append(
            {
                "text": f"Angular velocity norms: doubles ~{n.get('doubles')}"
                f"°/s, triples ~{n.get('triples')}°/s (Bruening 2018).",
                "lang": "en",
                "source": "KB science [A]",
                "url": n.get("source", ""),
                "kind": "science",
            }
        )
    meth = yaml.safe_load((KB / "methodology.yaml").read_text(encoding="utf-8"))
    for section, items in (meth or {}).items():
        for it in items:
            rows.append(
                {
                    "text": f"Methodology [{section}]: {' '.join(it['text'].split())}",
                    "lang": "en",
                    "source": f"methodology: {it['source']}",
                    "url": "",
                    "kind": "methodology",
                }
            )
    bib = yaml.safe_load((KB / "bibliography.yaml").read_text(encoding="utf-8"))
    for b in bib.get("books", []):
        rows.append(
            {
                "text": f"Book: {b['title']} - {b['eds']}. {b['what']}. Read for: {b['use_for']}.",
                "lang": "en",
                "source": "bibliography",
                "url": "",
                "kind": "book",
            }
        )
    for r_ in bib.get("regulations", []):
        rows.append(
            {
                "text": f"Rules: {r_['title']}. {r_['what']}",
                "lang": "en",
                "source": "ISU",
                "url": r_["url"],
                "kind": "rules",
            }
        )
    return rows


def _kb_yaml(name: str):
    return yaml.safe_load((KB_DIR / name).read_text(encoding="utf-8")) or {}
