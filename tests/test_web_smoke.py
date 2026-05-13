import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_plan_and_insights_render_without_external_services(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)

    from run import app

    client = app.test_client()
    assert client.get("/healthz").status_code == 200
    plan = client.get("/plan")
    assert plan.status_code == 200
    assert b"MongoDB sleep memory" in plan.data

    insights = client.get("/api/sleep/insights")
    assert insights.status_code == 200
    assert insights.get_json()["available"] is False
