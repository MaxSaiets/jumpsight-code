"""Security headers on all responses and on /healthz."""

from fastapi.testclient import TestClient


def test_security_headers_and_healthz():
    from jumpsight_app.web import app

    c = TestClient(app, base_url="http://localhost")
    for path in ("/", "/healthz", "/coach/names_uk"):
        r = c.get(path)
        assert r.headers.get("x-content-type-options") == "nosniff", path
        assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin", path
        assert "frame-ancestors 'self'" in (r.headers.get("content-security-policy") or ""), path
        assert "strict-transport-security" not in r.headers, path  # only on https
    h = c.get("/healthz")
    assert h.status_code == 200 and h.json()["ok"] is True
    hs = TestClient(app, base_url="https://localhost").get("/healthz")
    assert "max-age" in hs.headers.get("strict-transport-security", "")
