"""Tests for track visibility, tester tier, and scoped track access."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ---------------------------------------------------------------------------
# 1. Tester tier
# ---------------------------------------------------------------------------

def test_tester_tier_limits():
    from db.tiers import TIER_LIMITS
    assert "tester" in TIER_LIMITS
    assert TIER_LIMITS["tester"]["generations_per_month"] == 20
    assert TIER_LIMITS["tester"]["chat_per_day"] == 50


def test_tester_tier_in_set_tier(monkeypatch):
    from db.tiers import set_user_tier, TIER_LIMITS
    assert "tester" in TIER_LIMITS


def test_tester_tier_info(monkeypatch):
    """get_user_tier should return correct limits for testers."""
    from db.tiers import get_user_tier
    from unittest.mock import MagicMock
    from datetime import datetime, timezone

    mock_db = MagicMock()
    mock_db.users.find_one.return_value = {
        "_id": "u1",
        "tier": {
            "type": "tester",
            "generations_this_month": 5,
            "generation_month": datetime.now(timezone.utc).strftime("%Y-%m"),
        },
        "credits": {"balance": 0},
    }

    import db.tiers as tiers_mod
    monkeypatch.setattr(tiers_mod, "get_db", lambda: mock_db)

    info = get_user_tier("u1")
    assert info["type"] == "tester"
    assert info["generations_per_month"] == 20
    assert info["generations_remaining"] == 15
    assert info["can_generate"] is True
    assert info["is_admin"] is False


# ---------------------------------------------------------------------------
# 2. Track visibility — set_track_visibility
# ---------------------------------------------------------------------------

def test_set_visibility_invalid():
    from db.tracks import set_track_visibility
    ok, msg = set_track_visibility("t1", "bogus", "u1")
    assert ok is False
    assert "Invalid" in msg


def test_set_visibility_no_db(monkeypatch):
    import db.tracks as tracks_mod
    monkeypatch.setattr(tracks_mod, "get_db", lambda: None)
    from db.tracks import set_track_visibility
    ok, msg = set_track_visibility("t1", "published", "u1")
    assert ok is False


def test_set_visibility_wrong_owner(monkeypatch):
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.tracks.find_one.return_value = {
        "track_id": "t1", "generated_by": "other-user",
    }
    import db.tracks as tracks_mod
    monkeypatch.setattr(tracks_mod, "get_db", lambda: mock_db)

    from db.tracks import set_track_visibility
    ok, msg = set_track_visibility("t1", "published", "u1")
    assert ok is False
    assert "owner" in msg.lower()


def test_set_visibility_success(monkeypatch):
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.tracks.find_one.return_value = {
        "track_id": "t1", "generated_by": "u1",
    }
    import db.tracks as tracks_mod
    monkeypatch.setattr(tracks_mod, "get_db", lambda: mock_db)

    from db.tracks import set_track_visibility
    ok, msg = set_track_visibility("t1", "published", "u1")
    assert ok is True
    mock_db.tracks.update_one.assert_called_once()
    call_args = mock_db.tracks.update_one.call_args
    assert call_args[0][1]["$set"]["visibility"] == "published"


# ---------------------------------------------------------------------------
# 3. get_all_tracks scoping
# ---------------------------------------------------------------------------

def test_get_all_tracks_unscoped(monkeypatch):
    """Without user_id, get_all_tracks returns everything (no $or filter)."""
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.tracks.find.return_value = iter([])
    import db.tracks as tracks_mod
    monkeypatch.setattr(tracks_mod, "get_db", lambda: mock_db)

    from db.tracks import get_all_tracks
    get_all_tracks()

    query = mock_db.tracks.find.call_args[0][0]
    assert "$or" not in query


def test_get_all_tracks_scoped(monkeypatch):
    """With user_id, get_all_tracks filters to user's + public/published + presets."""
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.tracks.find.return_value = iter([])
    import db.tracks as tracks_mod
    monkeypatch.setattr(tracks_mod, "get_db", lambda: mock_db)

    from db.tracks import get_all_tracks
    get_all_tracks(user_id="u1")

    query = mock_db.tracks.find.call_args[0][0]
    assert "$or" in query
    or_clauses = query["$or"]
    assert {"generated_by": "u1"} in or_clauses
    assert {"is_preset": True} in or_clauses
    vis_clause = next(c for c in or_clauses if "visibility" in c)
    assert "public" in vis_clause["visibility"]["$in"]
    assert "published" in vis_clause["visibility"]["$in"]


# ---------------------------------------------------------------------------
# 4. get_public_tracks includes published
# ---------------------------------------------------------------------------

def test_get_public_tracks_includes_published(monkeypatch):
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.tracks.find.return_value = iter([])
    import db.tracks as tracks_mod
    monkeypatch.setattr(tracks_mod, "get_db", lambda: mock_db)

    from db.tracks import get_public_tracks
    get_public_tracks()

    query = mock_db.tracks.find.call_args[0][0]
    or_clauses = query["$or"]
    assert {"visibility": "published"} in or_clauses


# ---------------------------------------------------------------------------
# 5. Default visibility for new tracks
# ---------------------------------------------------------------------------

def test_user_track_default_private():
    """User-generated tracks should default to private visibility."""
    from audio.music_gen import _track_entry

    track = {
        "track_id": "t1", "title": "Test", "prompt": "test", "model": "lyria",
        "description": "", "local_path": "", "size_kb": 0,
        "mood_tags": [], "energy_level": "low", "avg_rating": None,
        "generated_by": "some-user", "visibility": "private",
    }
    entry = _track_entry(track)
    assert entry["visibility"] == "private"


def test_system_track_default_public():
    from audio.music_gen import _track_entry

    track = {
        "track_id": "t1", "title": "Test", "prompt": "test", "model": "lyria",
        "description": "", "local_path": "", "size_kb": 0,
        "mood_tags": [], "energy_level": "low", "avg_rating": None,
        "generated_by": "system", "visibility": "public",
    }
    entry = _track_entry(track)
    assert entry["visibility"] == "public"


# ---------------------------------------------------------------------------
# 6. Visibility endpoint
# ---------------------------------------------------------------------------

def test_visibility_endpoint(monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from web.app import create_app
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"uid": "test-uid", "name": "Test", "email": "t@t.com"}

        with patch("db.tracks.set_track_visibility", return_value=(True, "ok")):
            resp = client.post("/api/music/track-123/visibility",
                               json={"visibility": "published"},
                               content_type="application/json")

        assert resp.status_code == 200
        assert resp.get_json()["visibility"] == "published"


def test_visibility_endpoint_rejects_invalid(monkeypatch):
    from unittest.mock import patch

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from web.app import create_app
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"uid": "test-uid", "name": "Test", "email": "t@t.com"}

        with patch("db.tracks.set_track_visibility", return_value=(False, "Not the track owner")):
            resp = client.post("/api/music/track-123/visibility",
                               json={"visibility": "published"},
                               content_type="application/json")

        assert resp.status_code == 400
        assert "error" in resp.get_json()
