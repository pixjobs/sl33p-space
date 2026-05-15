"""Tests for agent consolidation: contextvars threading, get_recommendation, fallback logic."""

import os
import sys
import threading
import concurrent.futures

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
import pytest


# ---------------------------------------------------------------------------
# 1. contextvars threading
# ---------------------------------------------------------------------------

def test_set_get_user():
    from agent.agent import _set_user, _get_user
    _set_user("alice")
    assert _get_user() == "alice"
    _set_user("bob")
    assert _get_user() == "bob"


def test_user_ctx_default():
    """A fresh ContextVar (before any set) should return 'default'."""
    import contextvars
    fresh = contextvars.ContextVar("fresh_test", default="default")
    assert fresh.get() == "default"


def test_user_ctx_thread_isolation():
    """Each thread gets its own user_id — no cross-contamination."""
    from agent.agent import _set_user, _get_user

    results = {}
    barrier = threading.Barrier(2)

    def worker(name):
        _set_user(name)
        barrier.wait()          # both threads alive at the same time
        results[name] = _get_user()

    t1 = threading.Thread(target=worker, args=("user-A",))
    t2 = threading.Thread(target=worker, args=("user-B",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["user-A"] == "user-A"
    assert results["user-B"] == "user-B"


def test_user_ctx_threadpool_isolation():
    """ThreadPoolExecutor workers should each see their own user_id."""
    from agent.agent import _set_user, _get_user

    def work(uid):
        _set_user(uid)
        return _get_user()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        uids = [f"user-{i}" for i in range(8)]
        got = list(pool.map(work, uids))

    assert got == uids


# ---------------------------------------------------------------------------
# 2. _fallback_recommendation — pure logic, no I/O
# ---------------------------------------------------------------------------

def test_fallback_mood_match():
    from agent.agent import _fallback_recommendation

    insights = {
        "best_track": None,
        "mood_track_matrix": [
            {"mood": "stressed", "track": "Ocean Waves", "avg_rating": 4.5, "sessions": 3},
            {"mood": "calm", "track": "Forest Rain", "avg_rating": 4.0, "sessions": 2},
        ],
        "best_hour": 23,
        "current_streak": 4,
    }
    plan = {"available_tracks": ["Ocean Waves", "Forest Rain"], "playlist_id": "pl-1"}

    rec = _fallback_recommendation(insights, plan, mood="stressed")

    assert rec["soundscape_title"] == "Ocean Waves"
    assert "4.5" in rec["reasoning"]
    assert "3 sessions" in rec["reasoning"]
    assert "23:00" in rec["reasoning"]
    assert "4-night" in rec["reasoning"]
    assert rec["playlist_id"] == "pl-1"


def test_fallback_mood_match_insufficient_sessions():
    """If mood match has < 2 sessions, fall through to best_track."""
    from agent.agent import _fallback_recommendation

    insights = {
        "best_track": {"title": "Deep Hum", "avg_rating": 4.8},
        "mood_track_matrix": [
            {"mood": "wired", "track": "Buzz Cut", "avg_rating": 5.0, "sessions": 1},
        ],
        "best_hour": None,
        "current_streak": 0,
    }
    plan = {"available_tracks": ["Buzz Cut", "Deep Hum"], "playlist_id": "pl-2"}

    rec = _fallback_recommendation(insights, plan, mood="wired")

    assert rec["soundscape_title"] == "Deep Hum"
    assert "4.8" in rec["reasoning"]


def test_fallback_no_history():
    """Brand-new user: no best_track, no matrix, just pick the first available track."""
    from agent.agent import _fallback_recommendation

    insights = {
        "best_track": None,
        "mood_track_matrix": [],
        "best_hour": None,
        "current_streak": 0,
    }
    plan = {"available_tracks": ["Brown Noise"], "playlist_id": None}

    rec = _fallback_recommendation(insights, plan, mood="calm")

    assert rec["soundscape_title"] == "Brown Noise"
    assert "starting point" in rec["reasoning"].lower()


def test_fallback_empty_library():
    """No tracks at all — title should be None, but no crash."""
    from agent.agent import _fallback_recommendation

    insights = {
        "best_track": None,
        "mood_track_matrix": [],
        "best_hour": None,
        "current_streak": 0,
    }
    plan = {"available_tracks": [], "playlist_id": None}

    rec = _fallback_recommendation(insights, plan, mood="calm")

    assert rec["soundscape_title"] is None
    assert "playlist_id" in rec


def test_fallback_best_hour_appended():
    from agent.agent import _fallback_recommendation

    insights = {
        "best_track": {"title": "X", "avg_rating": 3.0},
        "mood_track_matrix": [],
        "best_hour": 22,
        "current_streak": 0,
    }
    plan = {"available_tracks": [], "playlist_id": None}

    rec = _fallback_recommendation(insights, plan, mood="calm")
    assert "22:00" in rec["reasoning"]


def test_fallback_streak_appended():
    from agent.agent import _fallback_recommendation

    insights = {
        "best_track": {"title": "X", "avg_rating": 3.0},
        "mood_track_matrix": [],
        "best_hour": None,
        "current_streak": 5,
    }
    plan = {"available_tracks": [], "playlist_id": None}

    rec = _fallback_recommendation(insights, plan, mood="calm")
    assert "5-night streak" in rec["reasoning"]


# ---------------------------------------------------------------------------
# 3. get_recommendation — integration (mocked I/O)
# ---------------------------------------------------------------------------

@pytest.fixture
def _mock_db(monkeypatch):
    """Stub out all database calls so get_recommendation runs without MongoDB."""
    import db.insights as insights_mod
    import db.sessions as sessions_mod
    import db.users as users_mod

    monkeypatch.setattr(insights_mod, "get_db", lambda: None)

    monkeypatch.setattr(sessions_mod, "get_recent_sessions", lambda uid, limit=7: [])
    monkeypatch.setattr(sessions_mod, "get_sleep_stats", lambda uid: {
        "total_sessions": 3, "avg_rating": 4.0, "top_sound": "Rain Loop",
    })

    monkeypatch.setattr(users_mod, "get_persona", lambda uid: None)

    import audio.music_gen as mg
    monkeypatch.setattr(mg, "list_generated_music", lambda: [
        {"title": "Rain Loop", "src": "/audio/rain.wav"},
        {"title": "Deep Hum", "src": "/audio/hum.wav"},
    ])

    import audio.playlist as pl
    monkeypatch.setattr(pl, "build_playlist", lambda mood, persona, uid: {
        "playlist_id": "mock-pl",
        "tracks": [{"title": "Rain Loop", "role": "settling", "energy_level": 0.3}],
    })


def test_get_recommendation_fallback_without_api_key(_mock_db, monkeypatch):
    """Without GOOGLE_API_KEY, get_recommendation should return the fallback."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from agent.agent import get_recommendation
    rec = get_recommendation("test-user", mood="calm")

    assert "soundscape_title" in rec
    assert "reasoning" in rec
    assert "playlist_id" in rec


def test_get_recommendation_sets_user_context(_mock_db, monkeypatch):
    """get_recommendation should set the user context for tool functions."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from agent.agent import get_recommendation, _get_user
    get_recommendation("uid-42", mood="tired")

    assert _get_user() == "uid-42"


def test_get_recommendation_gemini_error_falls_back(_mock_db, monkeypatch):
    """If Gemini call raises, should fall back gracefully."""
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    import agent.agent as aa
    monkeypatch.setattr(aa, "_adk_available", True)

    mock_genai = MagicMock()
    mock_genai.Client.return_value.models.generate_content.side_effect = RuntimeError("quota exceeded")

    with patch.dict("sys.modules", {"google.genai": mock_genai, "google": MagicMock()}):
        # Need to reimport to pick up the mock
        from agent.agent import get_recommendation
        rec = get_recommendation("test-user", mood="calm")

    assert "soundscape_title" in rec
    assert "reasoning" in rec


def _make_genai_mock(response_text):
    """Create a mock genai module with a preset response."""
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client
    return mock_genai


def test_get_recommendation_gemini_success(_mock_db, monkeypatch):
    """If Gemini returns valid JSON, that becomes the recommendation."""
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    import agent.agent as aa
    monkeypatch.setattr(aa, "_adk_available", True)

    mock_genai = _make_genai_mock(
        '{"soundscape_title": "Rain Loop", "reasoning": "4.0 avg rating across 3 sessions"}'
    )

    import sys
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
    monkeypatch.setitem(sys.modules, "google", MagicMock(genai=mock_genai))

    rec = aa.get_recommendation("test-user", mood="calm")

    assert rec["soundscape_title"] == "Rain Loop"
    assert "4.0" in rec["reasoning"]
    assert rec["playlist_id"] == "mock-pl"


def test_get_recommendation_strips_markdown_fences(_mock_db, monkeypatch):
    """Gemini sometimes wraps JSON in ```json ... ``` — should be stripped."""
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    import agent.agent as aa
    monkeypatch.setattr(aa, "_adk_available", True)

    mock_genai = _make_genai_mock(
        '```json\n{"soundscape_title": "Deep Hum", "reasoning": "great"}\n```'
    )

    import sys
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
    monkeypatch.setitem(sys.modules, "google", MagicMock(genai=mock_genai))

    rec = aa.get_recommendation("test-user", mood="calm")

    assert rec["soundscape_title"] == "Deep Hum"


# ---------------------------------------------------------------------------
# 4. Flask endpoint wiring
# ---------------------------------------------------------------------------

def test_recommend_endpoint_uses_agent(_mock_db, monkeypatch):
    """POST /api/sleep/recommend should delegate to get_recommendation."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from web.app import create_app
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"uid": "test-uid", "name": "Test", "email": "t@t.com"}

        resp = client.post("/api/sleep/recommend",
                           json={"mood": "stressed"},
                           content_type="application/json")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "soundscape_title" in data
    assert "reasoning" in data
