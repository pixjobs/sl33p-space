"""Tests for agent consolidation: contextvars threading, deterministic helpers, get_recommendation."""

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
# 2. _deterministic_pick — pure MongoDB logic, no LLM
# ---------------------------------------------------------------------------

def test_deterministic_pick_mood_match():
    """Mood match with >=2 sessions wins."""
    from agent.agent import _deterministic_pick

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

    title, reasoning = _deterministic_pick(insights, plan, mood="stressed")

    assert title == "Ocean Waves"
    assert "4.5" in reasoning
    assert "3 sessions" in reasoning
    assert "23:00" in reasoning
    assert "4-night" in reasoning


def test_deterministic_pick_insufficient_sessions_falls_to_best():
    """Mood match with <2 sessions falls through to best_track."""
    from agent.agent import _deterministic_pick

    insights = {
        "best_track": {"title": "Deep Hum", "avg_rating": 4.8},
        "mood_track_matrix": [
            {"mood": "wired", "track": "Buzz Cut", "avg_rating": 5.0, "sessions": 1},
        ],
        "best_hour": None,
        "current_streak": 0,
    }
    plan = {"available_tracks": ["Buzz Cut", "Deep Hum"], "playlist_id": "pl-2"}

    title, reasoning = _deterministic_pick(insights, plan, mood="wired")

    assert title == "Deep Hum"
    assert "4.8" in reasoning


def test_deterministic_pick_no_history():
    """Brand-new user: no best_track, no matrix, just pick first available."""
    from agent.agent import _deterministic_pick

    insights = {
        "best_track": None,
        "mood_track_matrix": [],
        "best_hour": None,
        "current_streak": 0,
    }
    plan = {"available_tracks": ["Brown Noise"], "playlist_id": None}

    title, reasoning = _deterministic_pick(insights, plan, mood="calm")

    assert title == "Brown Noise"
    assert "exploring" in reasoning.lower() or "clean start" in reasoning.lower()


def test_deterministic_pick_empty_library():
    """No tracks at all — title should be None, no crash."""
    from agent.agent import _deterministic_pick

    insights = {
        "best_track": None,
        "mood_track_matrix": [],
        "best_hour": None,
        "current_streak": 0,
    }
    plan = {"available_tracks": [], "playlist_id": None}

    title, reasoning = _deterministic_pick(insights, plan, mood="calm")

    assert title is None
    assert reasoning  # non-empty


def test_deterministic_pick_best_hour_appended():
    from agent.agent import _deterministic_pick

    insights = {
        "best_track": {"title": "X", "avg_rating": 3.0},
        "mood_track_matrix": [],
        "best_hour": 22,
        "current_streak": 0,
    }
    plan = {"available_tracks": [], "playlist_id": None}

    _, reasoning = _deterministic_pick(insights, plan, mood="calm")
    assert "22:00" in reasoning


def test_deterministic_pick_streak_appended():
    from agent.agent import _deterministic_pick

    insights = {
        "best_track": {"title": "X", "avg_rating": 3.0},
        "mood_track_matrix": [],
        "best_hour": None,
        "current_streak": 5,
    }
    plan = {"available_tracks": [], "playlist_id": None}

    _, reasoning = _deterministic_pick(insights, plan, mood="calm")
    assert "5-night" in reasoning


# ---------------------------------------------------------------------------
# 3. _build_plan_trace — reasoning trace from MongoDB data
# ---------------------------------------------------------------------------

def test_build_plan_trace_first_night():
    """No reviewed sessions yet — trace should call it out and still produce steps."""
    from agent.agent import _build_plan_trace

    insights = {
        "stats": {"reviewed_sessions": 0},
        "mood_track_matrix": [],
        "best_hour": None,
    }
    trace = _build_plan_trace(insights, [], mood="calm", chosen_title="Brown Noise")

    assert any("First night" in s["detail"] or "no prior data" in s["detail"].lower()
               for s in trace)
    assert any("Selected" in s["step"] for s in trace)


def test_build_plan_trace_mood_match_appears():
    from agent.agent import _build_plan_trace

    insights = {
        "stats": {"reviewed_sessions": 5, "avg_rating": 4.2},
        "mood_track_matrix": [
            {"mood": "stressed", "track": "Ocean", "avg_rating": 4.6, "sessions": 3},
        ],
        "best_hour": 23,
    }
    playlist = [
        {"title": "Ocean", "role": "settling"},
        {"title": "Hum", "role": "transition"},
        {"title": "Static", "role": "deep_sleep"},
    ]
    trace = _build_plan_trace(insights, playlist, mood="stressed", chosen_title="Ocean")

    text = " ".join(s["step"] + " " + s["detail"] for s in trace)
    assert "stressed" in text
    assert "Ocean" in text
    assert "23:00" in text
    assert "settling" in text  # arc string
    assert "Selected" in text


def test_build_plan_trace_factor_warning():
    """Challenging factor below 3.5 should generate a 'considered factors' step."""
    from agent.agent import _build_plan_trace

    insights = {
        "stats": {"reviewed_sessions": 4, "avg_rating": 3.8},
        "mood_track_matrix": [],
        "challenging_factor": {"factor": "screen_time", "avg_rating": 2.9},
        "best_hour": None,
    }
    trace = _build_plan_trace(insights, [], mood="calm", chosen_title="Hum")

    assert any("Screen Time" in s["detail"] and "2.9" in s["detail"] for s in trace)


# ---------------------------------------------------------------------------
# 4. _predict_outcome
# ---------------------------------------------------------------------------

def test_predict_outcome_first_night():
    from agent.agent import _predict_outcome
    assert "First night" in _predict_outcome({}, "calm", None)


def test_predict_outcome_mood_track_cell():
    from agent.agent import _predict_outcome
    insights = {
        "mood_track_matrix": [
            {"mood": "calm", "track": "Hum", "avg_rating": 4.4, "sessions": 5},
        ],
    }
    out = _predict_outcome(insights, "calm", "Hum")
    assert "4.4" in out
    assert "5 similar" in out


def test_predict_outcome_falls_back_to_track_average():
    from agent.agent import _predict_outcome
    insights = {
        "mood_track_matrix": [],
        "track_performance": [{"title": "Hum", "avg_rating": 3.9}],
    }
    out = _predict_outcome(insights, "calm", "Hum")
    assert "3.9" in out
    assert "new combination" in out.lower() or "exploring" in out.lower()


# ---------------------------------------------------------------------------
# 5. get_recommendation — integration (mocked I/O)
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


def test_get_recommendation_deterministic_without_api_key(_mock_db, monkeypatch):
    """Without GOOGLE_API_KEY, get_recommendation returns the deterministic plan."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from agent.agent import get_recommendation
    rec = get_recommendation("test-user", mood="calm")

    assert rec["source"] == "deterministic"
    assert "soundscape_title" in rec
    assert "reasoning" in rec
    assert "plan_trace" in rec
    assert isinstance(rec["plan_trace"], list)
    assert "predicted_outcome" in rec
    assert "confidence" in rec
    assert "playlist_arc" in rec
    assert rec["playlist_id"] == "mock-pl"


def test_get_recommendation_sets_user_context(_mock_db, monkeypatch):
    """get_recommendation should set the user context for tool functions."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from agent.agent import get_recommendation, _get_user
    get_recommendation("uid-42", mood="tired")

    assert _get_user() == "uid-42"


def test_get_recommendation_plan_trace_has_selected_step(_mock_db, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from agent.agent import get_recommendation
    rec = get_recommendation("test-user", mood="calm")

    steps = [s["step"] for s in rec["plan_trace"]]
    assert any("Selected" in s for s in steps)


def test_get_recommendation_gemini_error_falls_back(_mock_db, monkeypatch):
    """If Gemini call raises, should fall back to the deterministic plan."""
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    import agent.agent as aa
    monkeypatch.setattr(aa, "_adk_available", True)

    mock_genai = MagicMock()
    mock_genai.Client.return_value.models.generate_content.side_effect = RuntimeError("quota exceeded")

    with patch.dict("sys.modules", {"google.genai": mock_genai, "google": MagicMock()}):
        from agent.agent import get_recommendation
        rec = get_recommendation("test-user", mood="calm")

    # Falls back to deterministic — title and trace should still be present
    assert rec["source"] == "deterministic"
    assert rec["soundscape_title"]
    assert rec["plan_trace"]


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
    """Valid Gemini synthesis JSON populates vibe/reasoning/confidence; track stays deterministic."""
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    import agent.agent as aa
    monkeypatch.setattr(aa, "_adk_available", True)

    mock_genai = _make_genai_mock(
        '{"vibe": "midnight ocean to cathedral hush", '
        '"reasoning": "Rain Loop averages 4.0/5 across 3 sessions.", '
        '"confidence": 0.78}'
    )

    import sys
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
    monkeypatch.setitem(sys.modules, "google", MagicMock(genai=mock_genai))

    rec = aa.get_recommendation("test-user", mood="calm")

    # Track is chosen deterministically, not by LLM
    assert rec["soundscape_title"] == "Rain Loop"
    # Synthesis fields come from Gemini
    assert rec["vibe"] == "midnight ocean to cathedral hush"
    assert "4.0" in rec["reasoning"]
    assert rec["confidence"] == 0.78
    assert rec["source"] == "gemini"
    assert rec["playlist_id"] == "mock-pl"


def test_get_recommendation_clamps_confidence(_mock_db, monkeypatch):
    """Confidence values outside [0,1] should be clamped."""
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    import agent.agent as aa
    monkeypatch.setattr(aa, "_adk_available", True)

    mock_genai = _make_genai_mock(
        '{"vibe": "soft drift", "reasoning": "ok", "confidence": 1.7}'
    )

    import sys
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
    monkeypatch.setitem(sys.modules, "google", MagicMock(genai=mock_genai))

    rec = aa.get_recommendation("test-user", mood="calm")
    assert rec["confidence"] == 1.0


# ---------------------------------------------------------------------------
# 6. Flask endpoint wiring
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
    assert "plan_trace" in data
