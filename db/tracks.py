from datetime import datetime, timezone

try:
    from bson import ObjectId
except ImportError:  # Allows dev/demo mode without pymongo installed.
    class ObjectId(str):
        pass

from db import get_db


def ensure_indexes():
    db = get_db()
    if db is None:
        return
    db.tracks.create_index("track_id", unique=True)
    db.tracks.create_index("mood_tags")
    db.tracks.create_index([("generated_by", 1), ("archived", 1)])
    db.tracks.create_index("pack_id")


def upsert_track(data: dict) -> dict | None:
    db = get_db()
    if db is None:
        return None
    now = datetime.now(timezone.utc)
    track_id = data.get("track_id")
    if not track_id:
        return None

    doc = {
        "track_id": track_id,
        "title": data.get("title", ""),
        "prompt": data.get("prompt", ""),
        "full_prompt": data.get("full_prompt", ""),
        "description": data.get("description", ""),
        "model": data.get("model", ""),
        "format": data.get("format", "ogg/opus"),
        "size_kb": data.get("size_kb", 0),
        "duration_seconds": data.get("duration_seconds"),
        "gcs_bucket": data.get("gcs_bucket"),
        "gcs_object": data.get("gcs_object"),
        "gcs_url": data.get("gcs_url"),
        "local_path": data.get("local_path"),
        "storage_mode": data.get("storage_mode", "local"),
        "mood_tags": data.get("mood_tags", []),
        "mood_scores": data.get("mood_scores", {}),
        "energy_level": data.get("energy_level", "low"),
        "generated_by": data.get("generated_by", "system"),
        "is_preset": data.get("is_preset", False),
        "visibility": data.get("visibility", "public"),
        "archived": data.get("archived", False),
        "pack_id": data.get("pack_id"),
        "updated_at": now,
    }

    db.tracks.update_one(
        {"track_id": track_id},
        {
            "$set": doc,
            "$setOnInsert": {
                "play_count": 0,
                "avg_rating": None,
                "total_ratings": 0,
                "created_at": now,
            },
        },
        upsert=True,
    )
    return db.tracks.find_one({"track_id": track_id})


def get_track(track_id: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    return db.tracks.find_one({"track_id": track_id})


def get_all_tracks(include_archived: bool = False) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    query = {} if include_archived else {"archived": {"$ne": True}}
    cursor = db.tracks.find(query, sort=[("created_at", -1)])
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


def get_public_tracks() -> list[dict]:
    db = get_db()
    if db is None:
        return []
    cursor = db.tracks.find(
        {"$or": [{"generated_by": "system"}, {"is_preset": True}],
         "archived": {"$ne": True}},
        sort=[("created_at", -1)],
    )
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


def get_tracks_by_mood(mood: str, limit: int = 20) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    cursor = db.tracks.find(
        {"mood_tags": mood, "archived": {"$ne": True}},
        sort=[(f"mood_scores.{mood}", -1)],
    ).limit(limit)
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


def get_tracks_for_user(user_id: str) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    cursor = db.tracks.find(
        {"generated_by": user_id, "archived": {"$ne": True}},
        sort=[("created_at", -1)],
    )
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


def get_pack_tracks(pack_id) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    if isinstance(pack_id, str):
        pack_id = ObjectId(pack_id)
    cursor = db.tracks.find({"pack_id": pack_id, "archived": {"$ne": True}})
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


def archive_track(track_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    result = db.tracks.update_one(
        {"track_id": track_id},
        {"$set": {"archived": True, "updated_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count > 0


def unarchive_track(track_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    result = db.tracks.update_one(
        {"track_id": track_id},
        {"$set": {"archived": False, "updated_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count > 0


def delete_track(track_id: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    doc = db.tracks.find_one_and_delete({"track_id": track_id})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def update_track_stats(track_id: str, rating: int) -> bool:
    db = get_db()
    if db is None:
        return False
    track = db.tracks.find_one({"track_id": track_id})
    if not track:
        return False

    total = track.get("total_ratings", 0)
    avg = track.get("avg_rating") or 0
    new_total = total + 1
    new_avg = round(((avg * total) + rating) / new_total, 2)

    db.tracks.update_one(
        {"track_id": track_id},
        {
            "$set": {"avg_rating": new_avg, "total_ratings": new_total,
                     "updated_at": datetime.now(timezone.utc)},
            "$inc": {"play_count": 1},
        },
    )
    return True


def has_active_generation_job(user_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    return db.generation_jobs.count_documents(
        {"user_id": user_id, "status": {"$in": ["pending", "processing"]}},
        limit=1,
    ) > 0


def create_generation_job(user_id: str, prompt: str, title: str = "") -> str | None:
    db = get_db()
    if db is None:
        return None
    result = db.generation_jobs.insert_one({
        "user_id": user_id,
        "prompt": prompt,
        "title": title,
        "status": "pending",
        "result": None,
        "created_at": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)


def get_generation_job(job_id: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    try:
        doc = db.generation_jobs.find_one({"_id": ObjectId(job_id)})
    except Exception:
        return None
    if not doc:
        return None
    doc["_id"] = str(doc["_id"])
    for k in ("created_at", "completed_at"):
        if k in doc and doc[k]:
            doc[k] = doc[k].isoformat()
    return doc


def update_generation_job(job_id: str, status: str, result: dict = None):
    db = get_db()
    if db is None:
        return
    update = {"status": status}
    if result is not None:
        update["result"] = result
    if status in ("complete", "failed"):
        update["completed_at"] = datetime.now(timezone.utc)
    db.generation_jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": update},
    )


def resolve_track_url(track: dict) -> str:
    if track.get("gcs_url"):
        return track["gcs_url"]
    local = track.get("local_path", "")
    if local:
        import os
        return "/media/music/" + os.path.basename(local)
    return ""
