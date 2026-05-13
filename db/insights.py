from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from db import get_db


def _round(value: Any, digits: int = 1):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _default_insights(user_id: str, reason: str = "MongoDB is not connected") -> dict:
    return {
        "user_id": user_id,
        "available": False,
        "reason": reason,
        "summary": "Connect MongoDB and complete a few reviewed sessions to unlock personalized sleep insights.",
        "recommended_mood": "calm",
        "best_track": None,
        "best_mood": None,
        "best_factor": None,
        "challenging_factor": None,
        "trend": "not_enough_data",
        "stats": {
            "total_sessions": 0,
            "reviewed_sessions": 0,
            "avg_rating": None,
            "avg_duration": None,
        },
        "track_performance": [],
        "factor_correlations": [],
        "recent_pattern": [],
    }


def get_user_sleep_insights(user_id: str, days: int = 30) -> dict:
    """Return MongoDB-backed sleep insights for a user.

    This keeps the hackathon integration concrete: the coach and plan page can
    explain recommendations using session history, ratings, factors, and track
    performance stored in MongoDB rather than relying only on prompt context.
    """
    db = get_db()
    if db is None:
        return _default_insights(user_id)

    since = datetime.now(timezone.utc) - timedelta(days=days)
    match_user = {"user_id": user_id, "created_at": {"$gte": since}}
    reviewed_match = {
        **match_user,
        "status": "reviewed",
        "review.skipped": {"$ne": True},
        "review.rating": {"$ne": None},
    }

    stats_rows = list(db.sleep_sessions.aggregate([
        {"$match": reviewed_match},
        {"$group": {
            "_id": None,
            "reviewed_sessions": {"$sum": 1},
            "avg_rating": {"$avg": "$review.rating"},
            "avg_duration": {"$avg": "$actual.duration_minutes"},
        }},
    ]))
    stats_doc = stats_rows[0] if stats_rows else {}
    total_sessions = db.sleep_sessions.count_documents(match_user)

    track_rows = list(db.sleep_sessions.aggregate([
        {"$match": reviewed_match},
        {"$group": {
            "_id": "$plan.soundscape_title",
            "plays": {"$sum": 1},
            "avg_rating": {"$avg": "$review.rating"},
            "avg_duration": {"$avg": "$actual.duration_minutes"},
            "last_played": {"$max": "$created_at"},
        }},
        {"$match": {"_id": {"$nin": [None, ""]}}},
        {"$sort": {"avg_rating": -1, "plays": -1, "last_played": -1}},
        {"$limit": 5},
    ]))
    track_performance = [
        {
            "title": row.get("_id"),
            "plays": row.get("plays", 0),
            "avg_rating": _round(row.get("avg_rating")),
            "avg_duration": _round(row.get("avg_duration"), 0),
        }
        for row in track_rows
    ]

    mood_rows = list(db.sleep_sessions.aggregate([
        {"$match": reviewed_match},
        {"$group": {
            "_id": "$plan.mood",
            "sessions": {"$sum": 1},
            "avg_rating": {"$avg": "$review.rating"},
        }},
        {"$match": {"_id": {"$nin": [None, ""]}}},
        {"$sort": {"avg_rating": -1, "sessions": -1}},
        {"$limit": 1},
    ]))

    factor_rows = list(db.sleep_sessions.aggregate([
        {"$match": {**reviewed_match, "review.factors": {"$exists": True, "$ne": []}}},
        {"$unwind": "$review.factors"},
        {"$group": {
            "_id": "$review.factors",
            "sessions": {"$sum": 1},
            "avg_rating": {"$avg": "$review.rating"},
        }},
        {"$sort": {"avg_rating": -1, "sessions": -1}},
    ]))
    factor_correlations = [
        {
            "factor": row.get("_id"),
            "sessions": row.get("sessions", 0),
            "avg_rating": _round(row.get("avg_rating")),
        }
        for row in factor_rows
    ]

    recent_rows = list(db.sleep_sessions.find(
        {"user_id": user_id, "status": {"$in": ["completed", "reviewed"]}},
        sort=[("created_at", -1)],
        limit=7,
    ))
    recent_pattern = []
    for row in recent_rows:
        review = row.get("review") or {}
        created = row.get("created_at")
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        recent_pattern.append({
            "date": created.date().isoformat() if created else None,
            "track": row.get("plan", {}).get("soundscape_title"),
            "mood": row.get("plan", {}).get("mood"),
            "rating": review.get("rating"),
            "duration_minutes": row.get("actual", {}).get("duration_minutes"),
        })

    best_track = track_performance[0] if track_performance else None
    best_mood = mood_rows[0].get("_id") if mood_rows else None
    best_factor = factor_correlations[0] if factor_correlations else None
    challenging_factor = factor_correlations[-1] if len(factor_correlations) > 1 else None

    avg_rating = _round(stats_doc.get("avg_rating"))
    reviewed_sessions = stats_doc.get("reviewed_sessions", 0)
    if reviewed_sessions < 3:
        trend = "learning"
    elif avg_rating and avg_rating >= 4:
        trend = "working"
    elif avg_rating and avg_rating < 3:
        trend = "needs_adjustment"
    else:
        trend = "steady"

    if best_track:
        summary = f"MongoDB shows {best_track['title']} is your strongest recent track"
        if best_track.get("avg_rating"):
            summary += f" at {best_track['avg_rating']}/5 average"
        summary += "."
    elif reviewed_sessions:
        summary = "MongoDB has reviewed sessions, but no clear winning track yet. Keep rating sessions to improve recommendations."
    else:
        summary = "MongoDB is connected; complete and review a session to build personalized recommendations."

    return {
        "user_id": user_id,
        "available": True,
        "reason": None,
        "summary": summary,
        "recommended_mood": best_mood or "calm",
        "best_track": best_track,
        "best_mood": best_mood,
        "best_factor": best_factor,
        "challenging_factor": challenging_factor,
        "trend": trend,
        "stats": {
            "total_sessions": total_sessions,
            "reviewed_sessions": reviewed_sessions,
            "avg_rating": avg_rating,
            "avg_duration": _round(stats_doc.get("avg_duration"), 0),
        },
        "track_performance": track_performance,
        "factor_correlations": factor_correlations,
        "recent_pattern": recent_pattern,
    }
