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


def create_session(user_id: str, plan: dict,
                   playlist_id: str = None) -> str | None:
    db = get_db()
    if db is None:
        return None
    _auto_complete_stale(db, user_id)
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


def start_session(session_id: str, track: str = None) -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    result = db.sleep_sessions.update_one(
        {"_id": ObjectId(session_id), "status": "planned"},
        {"$set": {
            "status": "active",
            "actual.started_at": now,
            "actual.track_played": track,
            "updated_at": now,
        }},
    )
    return result.modified_count > 0


def end_session(session_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    session = db.sleep_sessions.find_one({"_id": ObjectId(session_id)})
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
                   metrics: dict = None) -> bool:
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
    db.sleep_sessions.update_one(
        {"_id": ObjectId(session_id), "status": "completed"},
        {"$set": {
            "status": "reviewed",
            "review": review_data,
            "updated_at": now,
        }},
    )
    return True


def skip_review(session_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    db.sleep_sessions.update_one(
        {"_id": ObjectId(session_id), "status": "completed"},
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
        {"user_id": user_id, "status": "completed"},
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


def update_session_factors(session_id: str, factors: list) -> bool:
    db = get_db()
    if db is None:
        return False
    valid_factors = {"caffeine", "exercise", "screen_time", "stress", "alcohol", "nap", "late_meal"}
    clean = [f for f in factors if f in valid_factors]
    now = datetime.now(timezone.utc)
    oid = ObjectId(session_id)
    session = db.sleep_sessions.find_one({"_id": oid})
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


def _auto_complete_stale(db, user_id: str):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_HOURS)
    db.sleep_sessions.update_many(
        {
            "user_id": user_id,
            "status": "active",
            "actual.started_at": {"$lt": cutoff},
        },
        {"$set": {
            "status": "completed",
            "actual.ended_at": cutoff,
            "updated_at": datetime.now(timezone.utc),
        }},
    )
