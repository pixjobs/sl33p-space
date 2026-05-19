from datetime import datetime, timezone, timedelta

try:
    from bson import ObjectId
except ImportError:  # Allows dev/demo mode without pymongo installed.
    class ObjectId(str):
        pass

from db import get_db

VALID_TRANSITIONS = {
    "planned": {"active", "skipped"},
    "active": {"completed"},
    "completed": {"reviewed"},
}

STALE_HOURS = 12


def create_manual_session(user_id: str, bed_time, wake_time, mood: str = "calm") -> str | None:
    db = get_db()
    if db is None:
        return None
    _force_complete_active(db, user_id)
    now = datetime.now(timezone.utc)
    if bed_time.tzinfo is None:
        bed_time = bed_time.replace(tzinfo=timezone.utc)
    if wake_time.tzinfo is None:
        wake_time = wake_time.replace(tzinfo=timezone.utc)
    duration = round((wake_time - bed_time).total_seconds() / 60)
    if duration < 0:
        duration = 0
    doc = {
        "user_id": user_id,
        "status": "completed",
        "plan": {
            "soundscape_id": None,
            "soundscape_title": "Manual log",
            "soundscape_src": None,
            "mood": mood,
        },
        "playlist_id": None,
        "actual": {
            "started_at": bed_time,
            "ended_at": wake_time,
            "duration_minutes": duration,
            "track_played": None,
            "tracks_played": 0,
            "manual": True,
        },
        "review": None,
        "created_at": now,
        "updated_at": now,
    }
    result = db.sleep_sessions.insert_one(doc)
    return str(result.inserted_id)


def create_session(user_id: str, plan: dict,
                   playlist_id: str = None) -> str | None:
    db = get_db()
    if db is None:
        return None
    _force_complete_active(db, user_id)
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "status": "planned",
        "plan": plan,
        "playlist_id": playlist_id,
        "actual": {
            "started_at": None,
            "ended_at": None,
            "duration_minutes": None,
            "track_played": None,
            "tracks_played": 0,
        },
        "review": None,
        "created_at": now,
        "updated_at": now,
    }
    result = db.sleep_sessions.insert_one(doc)
    return str(result.inserted_id)


def start_session(session_id: str, track: str = None,
                   user_id: str = None) -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    query = {"_id": ObjectId(session_id), "status": "planned"}
    if user_id:
        query["user_id"] = user_id
    result = db.sleep_sessions.update_one(
        query,
        {"$set": {
            "status": "active",
            "actual.started_at": now,
            "actual.track_played": track,
            "updated_at": now,
        }},
    )
    return result.modified_count > 0


def end_session(session_id: str, user_id: str = None) -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    query = {"_id": ObjectId(session_id)}
    if user_id:
        query["user_id"] = user_id
    session = db.sleep_sessions.find_one(query)
    if not session or session["status"] != "active":
        return False
    started = session["actual"].get("started_at")
    if started and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    duration = round((now - started).total_seconds() / 60) if started else 0
    update = {
        "status": "completed",
        "actual.ended_at": now,
        "actual.duration_minutes": duration,
        "updated_at": now,
    }
    db.sleep_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": update},
    )
    return True


def update_tracks_played(session_id: str, count: int) -> bool:
    db = get_db()
    if db is None:
        return False
    db.sleep_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"actual.tracks_played": count, "updated_at": datetime.now(timezone.utc)}},
    )
    return True


VALID_REVIEW_METRICS = {
    "quality": {"min": 1, "max": 5, "label": "Sleep Quality"},
    "depth": {"min": 1, "max": 5, "label": "Sleep Depth"},
    "interruptions": {"min": 0, "max": 5, "label": "Interruptions (0=none)"},
    "dream_recall": {"min": 0, "max": 5, "label": "Dream Recall"},
    "morning_energy": {"min": 1, "max": 5, "label": "Morning Energy"},
}


def review_session(session_id: str, rating: int = None, notes: str = "",
                   metrics: dict = None, user_id: str = None) -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    review_data = {"rating": rating, "notes": notes, "reviewed_at": now}
    if metrics:
        review_data["metrics"] = {}
        for key, val in metrics.items():
            if key in VALID_REVIEW_METRICS:
                review_data["metrics"][key] = val
    query = {"_id": ObjectId(session_id), "status": "completed"}
    if user_id:
        query["user_id"] = user_id
    db.sleep_sessions.update_one(
        query,
        {"$set": {
            "status": "reviewed",
            "review": review_data,
            "updated_at": now,
        }},
    )
    return True


def skip_review(session_id: str, user_id: str = None) -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    query = {"_id": ObjectId(session_id), "status": "completed"}
    if user_id:
        query["user_id"] = user_id
    db.sleep_sessions.update_one(
        query,
        {"$set": {
            "status": "reviewed",
            "review": {"skipped": True, "reviewed_at": now},
            "updated_at": now,
        }},
    )
    return True


def get_active_session(user_id: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    session = db.sleep_sessions.find_one(
        {"user_id": user_id, "status": {"$in": ["planned", "active"]}},
        sort=[("created_at", -1)],
    )
    if session:
        session["_id"] = str(session["_id"])
    return session


def get_pending_review(user_id: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    session = db.sleep_sessions.find_one(
        {
            "user_id": user_id,
            "status": "completed",
            "actual.started_at": {"$ne": None},
            "review.auto_completed": {"$ne": True},
        },
        sort=[("created_at", -1)],
    )
    if session:
        session["_id"] = str(session["_id"])
    return session


def get_recent_sessions(user_id: str, limit: int = 10) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    cursor = db.sleep_sessions.find(
        {"user_id": user_id, "status": "reviewed"},
        sort=[("created_at", -1)],
        limit=limit,
    )
    results = []
    for s in cursor:
        s["_id"] = str(s["_id"])
        results.append(s)
    return results


def get_sleep_stats(user_id: str) -> dict:
    db = get_db()
    if db is None:
        return {"avg_rating": None, "avg_duration": None, "total_sessions": 0, "top_sound": None}
    pipeline = [
        {"$match": {"user_id": user_id, "status": "reviewed",
                     "review.skipped": {"$ne": True}}},
        {"$group": {
            "_id": None,
            "avg_rating": {"$avg": "$review.rating"},
            "avg_duration": {"$avg": "$actual.duration_minutes"},
            "total": {"$sum": 1},
        }},
    ]
    result = list(db.sleep_sessions.aggregate(pipeline))
    stats = result[0] if result else {}

    top_pipeline = [
        {"$match": {"user_id": user_id, "status": "reviewed"}},
        {"$group": {"_id": "$plan.soundscape_title", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 1},
    ]
    top = list(db.sleep_sessions.aggregate(top_pipeline))

    return {
        "avg_rating": round(stats.get("avg_rating", 0) or 0, 1) or None,
        "avg_duration": round(stats.get("avg_duration", 0) or 0) or None,
        "total_sessions": stats.get("total", 0),
        "top_sound": top[0]["_id"] if top else None,
    }


def get_sessions_for_month(user_id: str, year: int, month: int) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    cursor = db.sleep_sessions.find(
        {
            "user_id": user_id,
            "status": {"$in": ["completed", "reviewed"]},
            "created_at": {"$gte": start, "$lt": end},
        },
        sort=[("created_at", 1)],
    )
    results = []
    for s in cursor:
        created = s.get("created_at")
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        review = s.get("review") or {}
        results.append({
            "session_id": str(s["_id"]),
            "day": created.day if created else 1,
            "rating": review.get("rating"),
            "duration": s.get("actual", {}).get("duration_minutes"),
            "track": s.get("plan", {}).get("soundscape_title"),
            "factors": review.get("factors", []),
            "notes": review.get("notes", ""),
        })
    return results


def update_session_factors(session_id: str, factors: list,
                           user_id: str = None) -> bool:
    db = get_db()
    if db is None:
        return False
    valid_factors = {"caffeine", "exercise", "screen_time", "stress", "alcohol", "nap", "late_meal"}
    clean = [f for f in factors if f in valid_factors]
    now = datetime.now(timezone.utc)
    oid = ObjectId(session_id)
    query = {"_id": oid}
    if user_id:
        query["user_id"] = user_id
    session = db.sleep_sessions.find_one(query)
    if not session or session["status"] not in ("completed", "reviewed"):
        return False
    if session.get("review") is None:
        db.sleep_sessions.update_one(
            {"_id": oid},
            {"$set": {"review": {"factors": clean}, "updated_at": now}},
        )
    else:
        db.sleep_sessions.update_one(
            {"_id": oid},
            {"$set": {"review.factors": clean, "updated_at": now}},
        )
    return True


def delete_session(session_id: str, user_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    result = db.sleep_sessions.delete_one(
        {"_id": ObjectId(session_id), "user_id": user_id}
    )
    return result.deleted_count > 0


def update_session_notes(session_id: str, notes: str,
                         user_id: str = None) -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    oid = ObjectId(session_id)
    query = {"_id": oid}
    if user_id:
        query["user_id"] = user_id
    session = db.sleep_sessions.find_one(query)
    if not session or session["status"] not in ("completed", "reviewed"):
        return False
    if session.get("review") is None:
        db.sleep_sessions.update_one(
            {"_id": oid},
            {"$set": {"review": {"notes": notes}, "updated_at": now}},
        )
    else:
        db.sleep_sessions.update_one(
            {"_id": oid},
            {"$set": {"review.notes": notes, "updated_at": now}},
        )
    return True


def _auto_complete_stale(db, user_id: str):
    """Auto-complete sessions that are clearly stale (older than STALE_HOURS).

    Auto-completed sessions are marked reviewed+skipped so they don't trigger
    review prompts for crashed/abandoned sessions.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_HOURS)
    now = datetime.now(timezone.utc)
    db.sleep_sessions.update_many(
        {
            "user_id": user_id,
            "status": "active",
            "actual.started_at": {"$lt": cutoff},
        },
        {"$set": {
            "status": "reviewed",
            "actual.ended_at": cutoff,
            "review": {"skipped": True, "reviewed_at": now, "auto_completed": True},
            "updated_at": now,
        }},
    )
    db.sleep_sessions.update_many(
        {
            "user_id": user_id,
            "status": "planned",
            "created_at": {"$lt": cutoff},
        },
        {"$set": {
            "status": "skipped",
            "updated_at": now,
        }},
    )


def _force_complete_active(db, user_id: str):
    """Force-complete any active/planned sessions when starting a new one.

    Unlike _auto_complete_stale, this has no age threshold — if a user starts
    a new session, any prior session is clearly over.
    """
    now = datetime.now(timezone.utc)
    db.sleep_sessions.update_many(
        {
            "user_id": user_id,
            "status": "active",
        },
        {"$set": {
            "status": "reviewed",
            "actual.ended_at": now,
            "review": {"skipped": True, "reviewed_at": now, "auto_completed": True},
            "updated_at": now,
        }},
    )
    db.sleep_sessions.update_many(
        {
            "user_id": user_id,
            "status": "planned",
        },
        {"$set": {
            "status": "skipped",
            "updated_at": now,
        }},
    )


def cleanup_stale_sessions(user_id: str) -> int:
    """Public entry point for stale session cleanup (called from page loads)."""
    db = get_db()
    if db is None:
        return 0
    _auto_complete_stale(db, user_id)
    return 0


def clear_stale_reviews(user_id: str) -> int:
    """Skip-review all completed sessions older than 1 hour (dev cleanup)."""
    db = get_db()
    if db is None:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    now = datetime.now(timezone.utc)
    result = db.sleep_sessions.update_many(
        {
            "user_id": user_id,
            "status": "completed",
            "updated_at": {"$lt": cutoff},
        },
        {"$set": {
            "status": "reviewed",
            "review": {"skipped": True, "reviewed_at": now, "auto_cleared": True},
            "updated_at": now,
        }},
    )
    return result.modified_count
