"""The journal is not a confirmation of review; the status belongs to the version of the analysis."""

import json

import pytest


@pytest.fixture
def account_store(monkeypatch, tmp_path):
    from jumpsight_coach import accounts, sessions

    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(accounts, "_uid", lambda: "coach_review_123")
    accounts._save(
        {
            "teams": {
                "coach_review_123": {"students": ["student_review_123"], "seen": {"student_review_123": 9999999999}}
            },
            "profiles": {},
            "codes": {},
        }
    )
    path = accounts.USERS / "student_review_123" / "history.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"job": "job_review_123", "ts": 1000, "jump": "Axel", "errors": []}]), encoding="utf-8")
    return accounts, path


def test_opening_history_does_not_mark_reviewed(account_store):
    accounts, _ = account_store
    before = accounts.STORE.read_bytes()
    rows = accounts.student_history("student_review_123")
    assert accounts.STORE.read_bytes() == before
    assert rows[0]["review_status"] == "pending"
    assert accounts.team()[0]["new"] == 1


def test_review_is_idempotent_and_new_content_requires_review(account_store):
    accounts, path = account_store
    row = accounts.student_history("student_review_123")[0]
    first = accounts.set_review_status("student_review_123", row["job"], row["review_version"], True)
    before = accounts.STORE.read_bytes()
    assert accounts.set_review_status("student_review_123", row["job"], row["review_version"], True) == first
    assert accounts.STORE.read_bytes() == before
    assert accounts.team()[0]["new"] == 0
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed[0]["errors"] = ["step_out"]
    path.write_text(json.dumps(changed), encoding="utf-8")
    assert accounts.team()[0]["new"] == 1
    with pytest.raises(accounts.ReviewConflict):
        accounts.set_review_status("student_review_123", row["job"], row["review_version"], True)


def test_cannot_review_another_students_job(account_store):
    accounts, _ = account_store
    with pytest.raises(PermissionError):
        accounts.set_review_status("student_outside_123", "job_review_123", "0" * 64, True)
    with pytest.raises(KeyError):
        accounts.set_review_status("student_review_123", "unknown_job", "0" * 64, True)


def test_corrupt_history_is_not_empty_team(account_store):
    accounts, path = account_store
    path.write_text('{"broken":', encoding="utf-8")
    with pytest.raises(accounts.HistoryUnavailable):
        accounts.student_history("student_review_123")


def test_review_api_reports_conflict_access_and_outage(account_store):
    from fastapi.testclient import TestClient

    from jumpsight_coach.api import app

    accounts, path = account_store
    client = TestClient(app, base_url="http://localhost")
    # The middleware receives its own temporary guest session; the _uid fixture
    # determines the rights of the tested coach without production accounts.
    client.post("/auth/guest")
    row = client.get("/team/student_review_123/history").json()[0]
    payload = {"job": row["job"], "version": row["review_version"], "reviewed": True}
    assert client.post("/team/student_review_123/review", json=payload).status_code == 200
    assert client.post("/team/student_outside_123/review", json=payload).status_code == 403
    assert client.post("/team/student_review_123/review", json={**payload, "job": "missing"}).status_code == 404
    assert client.post("/team/student_review_123/review", json={**payload, "version": "0" * 64}).status_code == 409
    path.write_text("{broken", encoding="utf-8")
    assert client.get("/team/student_review_123/history").status_code == 503
    assert client.post("/team/student_review_123/review", json=payload).status_code == 503
