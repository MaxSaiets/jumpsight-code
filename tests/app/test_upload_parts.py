"""A part can be repeated; a skipped one or a changed duplicate is not a success."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.fixture
def upload(tmp_path):
    meta = {"parts": 0, "bytes": 0, "ext": "webm", "uid": "guest_parts_123"}
    (tmp_path / "parts.json").write_text(json.dumps(meta), encoding="utf-8")
    return tmp_path


def test_same_part_retry_is_idempotent(upload):
    from jumpsight_app.upload_parts import append_part

    first = append_part(upload, 0, b"header", 100)
    again = append_part(upload, 0, b"header", 100)
    assert first[0] == again[0] == 200
    assert again[1]["duplicate"] is True
    assert (upload / "input.webm").read_bytes() == b"header"
    assert again[1]["parts"] == 1


def test_gap_conflicting_duplicate_and_limit_are_distinct(upload):
    from jumpsight_app.upload_parts import append_part

    assert append_part(upload, 1, b"next", 6)[0] == 409
    assert append_part(upload, 0, b"header", 6)[0] == 200
    assert append_part(upload, 0, b"different", 6)[0] == 409
    assert append_part(upload, 0, b"header", 6)[0] == 200
    assert append_part(upload, 1, b"next", 6)[0] == 413
    assert (upload / "input.webm").read_bytes() == b"header"


def test_concurrent_retries_only_append_once(upload):
    from jumpsight_app.upload_parts import append_part

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: append_part(upload, 0, b"header", 100), range(4)))
    assert all(status == 200 for status, _ in results)
    assert (upload / "input.webm").read_bytes() == b"header"


def test_uncommitted_tail_is_recovered_before_retry(upload):
    from jumpsight_app.upload_parts import append_part

    assert append_part(upload, 0, b"header", 100)[0] == 200
    with (upload / "input.webm").open("ab") as f:
        f.write(b"partial crash tail")
    assert append_part(upload, 1, b"next", 100)[0] == 200
    assert (upload / "input.webm").read_bytes() == b"headernext"


def test_committed_data_missing_fails_closed(upload):
    from jumpsight_app.upload_parts import append_part

    assert append_part(upload, 0, b"header", 100)[0] == 200
    (upload / "input.webm").write_bytes(b"he")
    assert append_part(upload, 1, b"next", 100)[0] == 503


def test_finished_upload_rejects_new_part(upload):
    from jumpsight_app.upload_parts import append_part

    append_part(upload, 0, b"header", 100)
    meta_path = upload / "parts.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["finished"] = True
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    assert append_part(upload, 0, b"header", 100)[0] == 200
    assert append_part(upload, 1, b"next", 100)[0] == 409


def test_http_parts_retry_and_finish_use_same_job(upload, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from jumpsight_app import webapp
    from jumpsight_coach import accounts, sessions

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    work = tmp_path / "work"
    job = "parts_job_123"
    folder = work / job
    folder.mkdir(parents=True)
    (folder / "parts.json").write_bytes((upload / "parts.json").read_bytes())
    monkeypatch.setattr(webapp, "WORK", work)
    monkeypatch.setattr(webapp, "JOBS", {})
    monkeypatch.setattr(webapp, "_probe_duration", lambda _: 1.0)
    dispatched = []
    monkeypatch.setattr(webapp, "_dispatch", lambda *args: dispatched.append(args))
    client = TestClient(webapp.build_app(), base_url="http://localhost")
    client.cookies.set("js_session", sessions.create("guest_parts_123"))
    url = f"/upload_part/{job}"
    assert client.post(url + "?seq=-1", content=b"header").status_code == 422
    assert client.post(url + "?seq=1", content=b"tail").status_code == 409
    assert client.post(url + "?seq=0", content=b"header").status_code == 200
    assert client.post(url + "?seq=0", content=b"header").json()["duplicate"] is True
    assert client.post(url + "?seq=0", content=b"different").status_code == 409
    assert client.post(url + "?seq=1", content=b"tail").status_code == 200
    assert (folder / "input.webm").read_bytes() == b"headertail"
    for _ in range(2):
        assert client.post(f"/upload_finish/{job}").status_code == 200
    assert len(dispatched) == 1
    assert client.post(url + "?seq=2", content=b"late").status_code == 409
    other = TestClient(client.app, base_url="http://localhost")
    other.cookies.set("js_session", sessions.create("other_parts_123"))
    assert other.post(url + "?seq=0", content=b"header").status_code == 404


@pytest.mark.requires_media
def test_invalid_video_cannot_use_client_duration(upload, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from jumpsight_app import webapp
    from jumpsight_coach import accounts, sessions

    work = tmp_path / "work"
    folder = work / "bad_video_123"
    folder.mkdir(parents=True)
    (folder / "parts.json").write_bytes((upload / "parts.json").read_bytes())
    monkeypatch.setattr(webapp, "WORK", work)
    monkeypatch.setattr(webapp, "JOBS", {})
    monkeypatch.setattr(webapp, "_probe_duration", lambda _: None)
    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    dispatched = []
    monkeypatch.setattr(webapp, "_dispatch", lambda *args: dispatched.append(args))
    client = TestClient(webapp.build_app(), base_url="http://localhost")
    client.cookies.set("js_session", sessions.create("guest_parts_123"))
    assert client.post("/upload_part/bad_video_123?seq=0", content=b"not a video").status_code == 200
    assert client.post("/upload_finish/bad_video_123?duration_s=10").status_code == 422
    assert dispatched == []


def test_preview_update_keeps_parts_and_appends_existing_preview_list(upload, monkeypatch, tmp_path):
    import subprocess
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from jumpsight_app import webapp
    from jumpsight_app.upload_parts import append_part
    from jumpsight_coach import accounts, sessions

    work = tmp_path / "work"
    folder = work / "preview_parts_123"
    folder.mkdir(parents=True)
    (folder / "parts.json").write_bytes((upload / "parts.json").read_bytes())
    append_part(folder, 0, b"header", 100)
    path = folder / "parts.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["previews"] = ["old_preview_123"]
    path.write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setattr(webapp, "WORK", work)
    monkeypatch.setattr(webapp, "JOBS", {"old_preview_123": {"state": "done", "uid": "guest_parts_123"}})
    monkeypatch.setattr(webapp, "_probe_duration", lambda _: 1.0)
    monkeypatch.setattr(webapp, "_dispatch", lambda *_: None)
    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setenv("JS_LIVE_PREVIEW", "1")

    def remux(command, **kwargs):
        from pathlib import Path

        Path(command[-1]).write_bytes(b"preview")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", remux)
    client = TestClient(webapp.build_app(), base_url="http://localhost")
    client.cookies.set("js_session", sessions.create("guest_parts_123"))
    assert client.post("/upload_part/preview_parts_123?seq=1", content=b"tail").status_code == 200
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["previews"] == ["old_preview_123", "preview_parts_123-p1"]
    assert saved["parts"] == 2 and saved["bytes"] == 10
    assert len(saved["part_hashes"]) == 2
