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


def _default_insights(user_id: str, reason: str = "not configured") -> dict:
    return {
        "user_id": user_id,
        "available": False,
        "reason": reason,
        "summary": "Start logging and reviewing your sleep to unlock personalised insights.",
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
        "best_hour": None,
        "best_hour_rating": None,
        "current_streak": 0,
        "longest_streak": 0,
        "mood_track_matrix": [],
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
            "avg_depth": {"$avg": "$review.metrics.depth"},
            "avg_energy": {"$avg": "$review.metrics.morning_energy"},
            "avg_interruptions": {"$avg": "$review.metrics.interruptions"},
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

    # ── Sleep window: best hour to start sleeping ──
    hour_rows = list(db.sleep_sessions.aggregate([
        {"$match": {**reviewed_match, "actual.started_at": {"$ne": None}}},
        {"$project": {
            "hour": {"$hour": "$actual.started_at"},
            "rating": "$review.rating",
        }},
        {"$group": {
            "_id": "$hour",
            "sessions": {"$sum": 1},
            "avg_rating": {"$avg": "$rating"},
        }},
        {"$match": {"sessions": {"$gte": 1}}},
        {"$sort": {"avg_rating": -1, "sessions": -1}},
    ]))
    best_hour = None
    best_hour_rating = None
    if hour_rows:
        best_hour = hour_rows[0]["_id"]
        best_hour_rating = _round(hour_rows[0]["avg_rating"])

    # ── Streak: consecutive days with sessions ──
    streak_rows = list(db.sleep_sessions.find(
        {"user_id": user_id, "status": {"$in": ["completed", "reviewed"]},
         "actual.started_at": {"$ne": None}},
        projection={"actual.started_at": 1},
        sort=[("actual.started_at", -1)],
        limit=90,
    ))
    current_streak = 0
    longest_streak = 0
    if streak_rows:
        seen_dates = set()
        for row in streak_rows:
            started = row.get("actual", {}).get("started_at")
            if started:
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                seen_dates.add(started.date())
        today = datetime.now(timezone.utc).date()
        run = 0
        check = today
        while check in seen_dates:
            run += 1
            check -= timedelta(days=1)
        if today not in seen_dates and (today - timedelta(days=1)) in seen_dates:
            check = today - timedelta(days=1)
            run = 0
            while check in seen_dates:
                run += 1
                check -= timedelta(days=1)
        current_streak = run
        sorted_dates = sorted(seen_dates)
        best_run = 1
        cur_run = 1
        for i in range(1, len(sorted_dates)):
            if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
                cur_run += 1
                best_run = max(best_run, cur_run)
            else:
                cur_run = 1
        longest_streak = best_run if sorted_dates else 0

    # ── Mood × Track effectiveness matrix ──
    mood_track_rows = list(db.sleep_sessions.aggregate([
        {"$match": {**reviewed_match,
                     "plan.mood": {"$nin": [None, ""]},
                     "plan.soundscape_title": {"$nin": [None, ""]}}},
        {"$group": {
            "_id": {"mood": "$plan.mood", "track": "$plan.soundscape_title"},
            "sessions": {"$sum": 1},
            "avg_rating": {"$avg": "$review.rating"},
        }},
        {"$sort": {"avg_rating": -1, "sessions": -1}},
        {"$limit": 10},
    ]))
    mood_track_matrix = [
        {
            "mood": row["_id"]["mood"],
            "track": row["_id"]["track"],
            "sessions": row["sessions"],
            "avg_rating": _round(row["avg_rating"]),
        }
        for row in mood_track_rows
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
        summary = f"Your best track is {best_track['title']}"
        if best_track.get("avg_rating"):
            summary += f" at {best_track['avg_rating']}/5"
        summary += "."
        avg_energy = _round(stats_doc.get("avg_energy"))
        avg_depth = _round(stats_doc.get("avg_depth"))
        if avg_energy and avg_depth:
            summary += f" Avg depth {avg_depth}/5, morning energy {avg_energy}/5."
    elif reviewed_sessions:
        summary = "No clear winning track yet. Keep rating sessions to sharpen recommendations."
    else:
        summary = "Complete and review a session to build personalised recommendations."

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
            "avg_depth": _round(stats_doc.get("avg_depth")),
            "avg_energy": _round(stats_doc.get("avg_energy")),
            "avg_interruptions": _round(stats_doc.get("avg_interruptions")),
        },
        "track_performance": track_performance,
        "factor_correlations": factor_correlations,
        "recent_pattern": recent_pattern,
        "best_hour": best_hour,
        "best_hour_rating": best_hour_rating,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "mood_track_matrix": mood_track_matrix,
    }
