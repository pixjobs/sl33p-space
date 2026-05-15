import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_healthz(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)

    from run import app
    client = app.test_client()
    assert client.get("/healthz").status_code == 200


def test_plan_redirects_without_auth(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)

    from run import app
    client = app.test_client()
    resp = client.get("/plan")
    assert resp.status_code == 302


def test_plan_renders_with_session(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)

    from run import app
    app.config["TESTING"] = True

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"uid": "smoke-test", "name": "Smoke", "email": "s@t.com"}
        resp = client.get("/plan")
        assert resp.status_code == 200


def test_insights_api_returns_json(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from run import app
    app.config["TESTING"] = True

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"uid": "smoke-test", "name": "Smoke", "email": "s@t.com"}
        resp = client.get("/api/sleep/insights")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "available" in data
