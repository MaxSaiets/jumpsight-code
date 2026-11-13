"""Neutral identifiers: cookie names and exercise ids carry no source-specific prefix."""

from fastapi.testclient import TestClient


def _web(monkeypatch, tmp_path):
    from jumpsight_coach import accounts, sessions

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(sessions, "_REMOTE", None)
    from jumpsight_app.web import app

    return app


def test_new_session_cookie_is_neutral(monkeypatch, tmp_path):
    app = _web(monkeypatch, tmp_path)
    c = TestClient(app, base_url="http://localhost")
    r = c.post("/coach/auth/guest")
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    assert any(c.startswith("js_session=") for c in cookies)
    assert all(c.startswith("js_") for c in cookies)


def test_kb_has_no_source_prefixed_ids_or_lesson_files_in_api():
    from jumpsight_coach.core import load_kb

    drills, _ = load_kb()
    prefixes = {d["id"].split("_")[0] for d in drills}
    assert prefixes <= {"ast", "backspin", "conte", "harness", "hv", "neg", "perna", "pw", "spinner"}
    from jumpsight_app.web import app

    body = TestClient(app, base_url="http://localhost").get("/coach/kb/list?lang=en").text
    assert "IMG_" not in body
