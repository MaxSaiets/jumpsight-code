"""Live recording goes straight to the worker through a queue, not through the shared volume.
Only pure logic lives here (no Modal): slicing a part to the queue item limit and assembling the file from items.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Measured in production: with the volume, the live worker saw the recording only after
# a commit by the web container and a reload on its side ('Jump found' in 6.6-9.6 s,
# the name in 15-22 s after landing; locally 3-7 s and ~11 s). The web container
# instead puts the bytes of each part with an offset into modal.Queue (partition =
# record id), and the worker assembles the file on ITS OWN disk, from items in any
# order, with repeats.

# modal.Queue item limit is 1 MiB including the service fields
MAX_CHUNK = 900_000


def split_part(offset: int, body: bytes, max_chunk: int = MAX_CHUNK) -> list[dict]:
    """Recording part -> queue items {"o": offset in the file, "b": bytes}."""
    return [{"o": offset + i, "b": body[i : i + max_chunk]} for i in range(0, len(body), max_chunk)]


class ChunkSink:
    """Local copy of the recording that run_live_loop reads: input.<ext> and parts.json.

    Items may arrive out of order (several send threads) and twice
    (a retry after a network failure). In parts.json, 'bytes' is only the contiguous
    prefix: the scanner must not see a hole in the middle of the file.
    """

    def __init__(self, directory: Path, ext: str, uid: str | None, started: float):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ext = ext if ext in ("webm", "mp4", "mkv") else "webm"
        self.src = self.dir / f"input.{self.ext}"
        self.src.touch()
        self.meta = {"ext": self.ext, "uid": uid, "parts": 0, "bytes": 0, "started": started, "finished": False}
        self._pending: dict[int, bytes] = {}
        self._save()

    @property
    def contiguous(self) -> int:
        return int(self.meta["bytes"])

    @property
    def finished(self) -> bool:
        return bool(self.meta["finished"])

    def _save(self) -> None:
        tmp = self.dir / "parts.json.tmp"
        tmp.write_text(json.dumps(self.meta), encoding="utf-8")
        os.replace(tmp, self.dir / "parts.json")

    def apply(self, items: list[dict]) -> bool:
        """Write the items; True if the contiguous prefix grew or the end was reached."""
        grew = False
        for it in items:
            if it.get("end"):
                if not self.meta["finished"]:
                    self.meta["finished"] = True
                    grew = True
                continue
            o, b = int(it["o"]), bytes(it["b"])
            if o + len(b) <= self.contiguous:
                continue  # a repeat of an item already written
            self._pending[o] = b
        with self.src.open("r+b") as f:
            while True:
                start = self.contiguous
                # an item that starts within the prefix (a repeat may overlap)
                hit = next((o for o in sorted(self._pending) if o <= start), None)
                if hit is None:
                    break
                b = self._pending.pop(hit)
                tail = b[start - hit :]
                if not tail:
                    continue
                f.seek(start)
                f.write(tail)
                self.meta["bytes"] = start + len(tail)
                self.meta["parts"] = int(self.meta["parts"]) + 1
                grew = True
            f.flush()
        if grew:
            self._save()
        return grew
