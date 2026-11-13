"""Regression of the access boundary between the old UID and the server-side session."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _session_client(app, uid: str) -> TestClient:
    from jumpsight_coach import sessions

    client = TestClient(app, base_url="http://localhost")
    client.cookies.set("js_session", sessions.create(uid))
    return client


def _isolated(monkeypatch, tmp_path):
    from jumpsight_app import webapp
    from jumpsight_coach import accounts, sessions

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(webapp, "WORK", tmp_path / "web")
    webapp.JOBS.clear()


def test_registered_account_ignores_forged_uid_and_requires_login(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach.api import app

    email = "owner@example.test"
    user = TestClient(app, base_url="http://localhost")
    owner = user.post("/auth/guest").json()["uid"]
    r = user.post("/auth/register", json={"email": email, "password": "strong-pass-123"})
    assert r.status_code == 200
    assert user.get("/me").json()["uid"] == owner
    assert "httponly" in r.headers["set-cookie"].lower()

    attacker = TestClient(app, base_url="http://localhost", headers={"X-App-User": owner})
    assert attacker.get("/me").status_code == 403
    assert attacker.post("/me", json={"name": "stolen"}).status_code == 403
    assert attacker.post("/claim", json={"token": "not-a-transfer"}).status_code == 404

    # A current user with an old localStorage UID logs in again with a password.
    r = attacker.post("/auth/login", json={"email": email, "password": "strong-pass-123"})
    assert r.status_code == 200
    assert attacker.get("/me").json()["uid"] == owner
    logged_out = attacker.post("/auth/logout")
    assert logged_out.status_code == 200
    assert attacker.get("/me").json()["uid"] == logged_out.json()["uid"]
    assert logged_out.json()["uid"] != owner


def test_guest_claim_and_job_access(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_app import webapp
    from jumpsight_coach.api import app as coach_app

    guest = _session_client(coach_app, "guest_owner_123")
    token = guest.post("/auth/transfer").json()["token"]
    moved = TestClient(coach_app, base_url="http://localhost")
    assert moved.post("/claim", json={"token": token}).json()["uid"] == "guest_owner_123"
    assert moved.get("/me").json()["uid"] == "guest_owner_123"

    webapp.JOBS["owned123"] = {
        "uid": "guest_owner_123",
        "state": "done",
        "started": 1.0,
        "name": "clip.mp4",
        "events": [],
    }
    app = webapp.build_app()
    stranger = _session_client(app, "other_guest_123")
    assert stranger.get("/status/owned123").status_code == 404
    assert stranger.get("/summary/owned123").status_code == 404
    assert stranger.get("/media/owned123/full/original").status_code == 404
    owner = _session_client(app, "guest_owner_123")
    assert owner.get("/status/owned123").status_code == 200


def test_cross_origin_write_is_rejected(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach.api import app

    client = _session_client(app, "guest_origin_123")
    r = client.post("/me", json={"name": "bad"}, headers={"Origin": "https://attacker.example"})
    assert r.status_code == 403


def test_claim_rate_limit_and_session_expiry(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach import sessions
    from jumpsight_coach.api import app

    client = _session_client(app, "guest_limit_123")
    for _ in range(12):
        assert client.post("/claim", json={"token": "BADBAD"}).status_code == 404
    assert client.post("/claim", json={"token": "BADBAD"}).status_code == 429

    token = sessions.create("guest_limit_123")
    assert sessions.resolve(token) == "guest_limit_123"
    sessions.revoke(token)
    assert sessions.resolve(token) is None


def test_remote_session_store_is_shared_and_revocable(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach import sessions

    class Store(dict):
        def put(self, key, value):
            self[key] = value

    store = Store()
    sessions.use_remote(store)
    try:
        token = sessions.create("guest_remote_123")
        assert sessions.resolve(token) == "guest_remote_123"
        sessions.revoke(token)
        assert sessions.resolve(token) is None
    finally:
        sessions.use_remote(None)


def test_corrupt_accounts_store_fails_closed(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach import accounts

    accounts.STORE.write_text("{broken", encoding="utf-8")
    try:
        accounts.is_registered("guest_broken_123")
    except RuntimeError as exc:
        assert "unreadable" in str(exc)
    else:
        raise AssertionError("corrupt account state must not be treated as empty")


def test_mounted_app_uses_same_session_for_coach_and_video(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    monkeypatch.setenv("JS_SKIP_WARMUP", "1")
    from jumpsight_app import web, webapp

    app = web.build()
    owner = TestClient(app, base_url="http://localhost")
    uid = owner.post("/coach/auth/guest").json()["uid"]
    result = owner.post("/coach/auth/register", json={"email": "shared@example.test", "password": "strong-pass-123"})
    assert result.status_code == 200
    webapp.JOBS["mounted123"] = {"uid": uid, "state": "done", "started": 1.0, "name": "clip.mp4", "events": []}
    assert owner.get("/status/mounted123").status_code == 200
    assert owner.get("/coach/me").json()["uid"] == uid
    attacker = TestClient(app, base_url="http://localhost", headers={"X-App-User": uid})
    assert attacker.get("/status/mounted123").status_code == 404
    assert attacker.get("/coach/me").status_code == 403


def test_private_stem_requires_own_history(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    import json

    from jumpsight_coach import accounts
    from jumpsight_coach.api import app

    history = accounts.USERS / "stem_owner_123" / "history.json"
    history.parent.mkdir(parents=True)
    history.write_text(json.dumps([{"stem": "private_jump", "job": "job123"}]), encoding="utf-8")
    owner = _session_client(app, "stem_owner_123")
    stranger = _session_client(app, "other_guest_123")
    assert owner.get("/avatar3d/private_jump/status").json()["state"] == "absent"
    assert stranger.get("/avatar3d/private_jump/status").status_code == 404
    assert stranger.get("/video/private_jump").status_code == 404
    assert stranger.get("/out_json/private_jump").status_code == 404


def test_ownerless_video_job_is_denied_to_everyone(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_app import webapp

    app = webapp.build_app()
    webapp.JOBS["orphan123"] = {"state": "done", "started": 1.0, "name": "clip.mp4", "events": []}
    anonymous = TestClient(app, base_url="http://localhost")
    member = _session_client(app, "member_123")
    for client in (anonymous, member):
        assert client.get("/status/orphan123").status_code == 404
        assert client.get("/summary/orphan123").status_code == 404
        assert client.post("/cancel/orphan123").status_code == 404


def test_coach_needs_student_acceptance_before_history(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach.api import app

    coach = _session_client(app, "coach_12345")
    student = _session_client(app, "student_12345")
    coach_code = coach.get("/me").json()["code"]
    student_code = student.get("/me").json()["code"]
    assert coach.post("/team/add", json={"code": student_code}).json()["state"] == "pending"
    assert coach.get("/team/pending").json()[0]["uid"] == "student_12345"
    assert student.get("/me").json()["pending_coach"]["code"] == coach_code
    assert coach.get("/team/student_12345/history").status_code == 403
    assert student.post("/link/accept", json={"code": coach_code}).status_code == 200
    assert coach.get("/team/student_12345/history").status_code == 200
    from jumpsight_app import webapp

    webapp.JOBS["coachjob123"] = {"uid": "student_12345", "state": "done"}
    assert coach.post("/comment", json={"job": "coachjob123", "text": "Good"}).status_code == 200
    assert coach.post("/share", json={"job": "coachjob123"}).status_code == 200
    assert student.post("/coach/leave").status_code == 200
    assert coach.get("/team/student_12345/history").status_code == 403
    assert coach.post("/comment", json={"job": "coachjob123", "text": "No"}).status_code == 403
    assert coach.post("/share", json={"job": "coachjob123"}).status_code == 403


def test_third_coach_cannot_replace_accepted_link(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach.api import app

    coach_a = _session_client(app, "coach_a_12345")
    coach_b = _session_client(app, "coach_b_12345")
    student = _session_client(app, "student_b_12345")
    student_code = student.get("/me").json()["code"]
    coach_a_code = coach_a.get("/me").json()["code"]
    assert coach_a.post("/team/add", json={"code": student_code}).status_code == 200
    assert student.post("/link/accept", json={"code": coach_a_code}).status_code == 200
    assert coach_b.post("/team/add", json={"code": student_code}).status_code == 403


def test_expired_pending_link_cannot_be_accepted(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach import accounts
    from jumpsight_coach.api import app

    coach = _session_client(app, "coach_exp_12345")
    student = _session_client(app, "student_exp_12345")
    coach_code = coach.get("/me").json()["code"]
    student_code = student.get("/me").json()["code"]
    assert coach.post("/team/add", json={"code": student_code}).status_code == 200
    data = json.loads(accounts.STORE.read_text(encoding="utf-8"))
    data["links"]["coach_exp_12345:student_exp_12345"]["expires_at"] = 0
    accounts.STORE.write_text(json.dumps(data), encoding="utf-8")
    assert student.post("/link/accept", json={"code": coach_code}).status_code == 404


def test_student_can_reject_pending_link(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach.api import app

    coach = _session_client(app, "coach_rej_12345")
    student = _session_client(app, "student_rej_12345")
    coach_code = coach.get("/me").json()["code"]
    assert coach.post("/team/add", json={"code": student.get("/me").json()["code"]}).status_code == 200
    assert student.post("/link/reject", json={"code": coach_code}).status_code == 200
    assert student.get("/me").json()["pending_coach"] is None
    assert student.post("/link/accept", json={"code": coach_code}).status_code == 404


def test_share_expiry_and_revoke_close_existing_cookie(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach import accounts

    token = "share_token_123"
    accounts.STORE.write_text(
        json.dumps(
            {
                "codes": {},
                "profiles": {},
                "teams": {},
                "links": {},
                "comments": {},
                "shares": {token: {"job": "job123", "scope": "read", "expires_at": 0, "revoked_at": None}},
            }
        ),
        encoding="utf-8",
    )
    assert accounts.job_for_share(token) is None
    assert accounts.can_view_job("owner_123", None, "job123", token) is False


def test_share_token_is_limited_to_its_own_job(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from jumpsight_coach import accounts

    token = "share_scope_123"
    accounts.STORE.write_text(
        json.dumps(
            {
                "codes": {},
                "profiles": {},
                "teams": {},
                "links": {},
                "comments": {},
                "shares": {token: {"job": "job123", "scope": "read", "expires_at": 9999999999, "revoked_at": None}},
            }
        ),
        encoding="utf-8",
    )
    assert accounts.can_view_job("owner_123", None, "job123", token) is True
    assert accounts.can_view_job("owner_456", None, "job456", token) is False
