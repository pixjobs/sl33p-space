import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_insights_fallback_without_mongodb(monkeypatch):
    import db.insights as insights

    monkeypatch.setattr(insights, "get_db", lambda: None)

    data = insights.get_user_sleep_insights("user-1")

    assert data["available"] is False
    assert data["recommended_mood"] == "calm"
    assert data["stats"]["total_sessions"] == 0
    assert "MongoDB" in data["summary"]
