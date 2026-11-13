"""Sequential live upload: exact repeats without duplicating bytes.

The lock works within one process. Cloud horizontal scaling needs a separate shared store/coordinator; this module does not imitate one.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

LOCK = threading.Lock()


def save_meta(path: Path, meta: dict) -> None:
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


def append_part(directory: Path, seq: int, body: bytes, max_bytes: int) -> tuple[int, dict]:
    """Confirms only the written part or its exact verified duplicate."""
    with LOCK:
        path = directory / "parts.json"
        if not path.is_file():
            return 404, {"error": "unknown upload"}
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
            expected, committed = int(meta["parts"]), int(meta["bytes"])
            if meta["ext"] not in ("webm", "mp4", "mkv") or expected < 0 or committed < 0:
                raise ValueError("invalid metadata")
            source = directory / f"input.{meta['ext']}"
            size = source.stat().st_size if source.exists() else 0
            if size < committed:
                return 503, {"error": "upload storage incomplete"}
            digest = hashlib.sha256(body).hexdigest()
            hashes = meta.setdefault("part_hashes", {})
            if not isinstance(hashes, dict):
                raise ValueError("invalid part hashes")
            if seq < expected and hashes.get(str(seq)) == digest:
                return 200, {"ok": True, "duplicate": True, "parts": expected, "bytes": committed}
            if seq != expected:
                return 409, {"error": "out of order or conflicting duplicate", "expected": expected}
            if meta.get("finished"):
                return 409, {"error": "upload finished", "expected": expected}
            if not body:
                return 422, {"error": "empty part"}
            if committed + len(body) > max_bytes:
                return 413, {"error": f"file larger than {max_bytes // (1 << 20)} MB"}
            # After a break between append and commit, remove the unconfirmed tail.
            with source.open("r+b" if source.exists() else "w+b") as f:
                f.truncate(committed)
                f.seek(committed)
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            meta["parts"] = expected + 1
            meta["bytes"] = committed + len(body)
            hashes[str(seq)] = digest
            save_meta(path, meta)
            return 200, {"ok": True, "parts": meta["parts"], "bytes": meta["bytes"]}
        except (OSError, ValueError, KeyError, TypeError):
            return 503, {"error": "upload storage unavailable"}
