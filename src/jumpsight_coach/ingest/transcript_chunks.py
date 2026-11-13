"""Stage 1b of the ingestion: subtitles of coaching videos -> timed chunks.

    python -m jumpsight_coach.ingest.transcript_chunks VTT_DIR --manifest TITLES.json [--out FILE]

Input:  a folder of .vtt subtitle files named <video_id>.*.vtt, and a manifest
        JSON {"<video_id>": "<title>"} that you supply (nothing is built in).
Output: STATE_DIR/lesson_library/library_chunks.jsonl (or --out), one chunk
        per line: {video_id, title, url_ts, t0, text}. The chunks are a local
        search index only; answers carry a paraphrase plus the timed link.

Transcribing a video's own audio is done by
`jumpsight_mascot.voice.narrate.transcribe_lesson`.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from jumpsight_core.paths import LESSON_LIBRARY_DIR

_TS = re.compile(r"(\d+):(\d+):(\d+)\.(\d+) --> ")
_TAG = re.compile(r"<[^>]+>")


def parse_vtt(path: Path) -> list[tuple[float, str]]:
    """[(second, text line)] without the duplicates of neighbouring auto-captions."""
    out, last = [], ""
    t = 0.0
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _TS.match(ln)
        if m:
            h, mi, s, _ = map(int, m.groups())
            t = h * 3600 + mi * 60 + s
            continue
        txt = _TAG.sub("", ln).strip()
        if not txt or txt == last or "-->" in txt or txt.isdigit() or txt.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        out.append((t, txt))
        last = txt
    return out


def chunk(lines: list[tuple[float, str]], words_per: int = 60) -> list[dict]:
    chunks, buf, t0 = [], [], 0.0
    for t, txt in lines:
        if not buf:
            t0 = t
        buf += txt.split()
        if len(buf) >= words_per:
            chunks.append({"t0": t0, "text": " ".join(buf)})
            buf = []
    if len(buf) >= 15:
        chunks.append({"t0": t0, "text": " ".join(buf)})
    return chunks


def build(vtt_dir: str | Path, manifest: str | Path, out: str | Path | None = None) -> int:
    titles = json.loads(Path(manifest).read_text(encoding="utf-8"))
    dest = Path(out) if out else LESSON_LIBRARY_DIR / "library_chunks.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    seen = set()
    for f in sorted(Path(vtt_dir).glob("*.vtt")):
        vid = f.name.split(".")[0]
        if vid in seen:  # en / en-orig duplicates - keep the first
            continue
        seen.add(vid)
        for ch in chunk(parse_vtt(f)):
            rows.append(
                {
                    "video_id": vid,
                    "title": titles.get(vid, vid),
                    "url_ts": f"https://www.youtube.com/watch?v={vid}&t={int(ch['t0'])}s",
                    "t0": ch["t0"],
                    "text": ch["text"],
                }
            )
    dest.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print(f"{dest}: {len(rows)} chunks from {len(seen)} videos")
    return len(rows)


def load_corpus(path: str | Path | None = None) -> list[dict]:
    f = Path(path) if path else LESSON_LIBRARY_DIR / "library_chunks.jsonl"
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("vtt_dir")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    build(a.vtt_dir, a.manifest, a.out)
