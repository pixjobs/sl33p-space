from datetime import datetime, timezone, timedelta

from bson import ObjectId

from db import get_db

VALID_TRANSITIONS = {
    "planned": {"active", "skipped"},
    "active": {"completed"},
    "completed": {"reviewed"},
}

STALE_HOURS = 12


def create_session(user_id: str, plan: dict) -> str | None:
    db = get_db()
    if db is None:
        return None
    _auto_complete_stale(db, user_id)
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "status": "planned",
        "plan": plan,
        "actual": {
            "started_at": None,
            "ended_at": None,
            "duration_minutes": None,
            "track_played": None,
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
    duration = round((now - started).total_seconds() / 60) if started else 0
    db.sleep_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {
            "status": "completed",
            "actual.ended_at": now,
            "actual.duration_minutes": duration,
            "updated_at": now,
        }},
    )
    return True


def review_session(session_id: str, rating: int, notes: str = "") -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    db.sleep_sessions.update_one(
        {"_id": ObjectId(session_id), "status": "completed"},
        {"$set": {
            "status": "reviewed",
            "review": {
                "rating": rating,
                "notes": notes,
                "reviewed_at": now,
            },
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
