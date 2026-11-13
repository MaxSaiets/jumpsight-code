"""Live recording through the queue: the worker file is the web container file."""

import json
import random

from jumpsight_app.live_queue import ChunkSink, split_part


def _parts(n=12, size=2500):
    rnd = random.Random(7)
    return [bytes(rnd.getrandbits(8) for _ in range(size + i * 13)) for i in range(n)]


def _items(parts, max_chunk):
    out, off = [], 0
    for p in parts:
        out += split_part(off, p, max_chunk=max_chunk)
        off += len(p)
    return out


def test_in_order_rebuilds_the_same_file(tmp_path):
    parts = _parts()
    sink = ChunkSink(tmp_path, "webm", "u1", 1.0)
    for it in _items(parts, 1000):
        sink.apply([it])
    assert (tmp_path / "input.webm").read_bytes() == b"".join(parts)
    meta = json.loads((tmp_path / "parts.json").read_text(encoding="utf-8"))
    assert meta["bytes"] == sum(map(len, parts)) and meta["uid"] == "u1" and not meta["finished"]


def test_shuffled_and_duplicated_items_never_expose_a_hole(tmp_path):
    parts = _parts()
    items = _items(parts, 700)
    items += items[3:9]  # retries after a network failure
    random.Random(3).shuffle(items)
    sink = ChunkSink(tmp_path, "webm", None, 1.0)
    whole = b"".join(parts)
    for it in items:
        sink.apply([it])
        n = sink.contiguous
        # a prefix that the scanner sees is always gap-free and matches the original
        assert (tmp_path / "input.webm").read_bytes()[:n] == whole[:n]
    assert sink.contiguous == len(whole)


def test_end_marker_finishes(tmp_path):
    sink = ChunkSink(tmp_path, "mp4", None, 1.0)
    sink.apply(split_part(0, b"abc") + [{"end": True}])
    meta = json.loads((tmp_path / "parts.json").read_text(encoding="utf-8"))
    assert meta["finished"] and meta["bytes"] == 3 and meta["ext"] == "mp4"


def test_split_respects_queue_item_limit():
    items = split_part(10, b"x" * 2_000_000)
    assert all(len(it["b"]) <= 900_000 for it in items)
    assert items[0]["o"] == 10 and items[-1]["o"] + len(items[-1]["b"]) == 2_000_010
