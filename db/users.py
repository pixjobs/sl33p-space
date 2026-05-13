from datetime import datetime, timezone

from db import get_db

DEFAULT_PREFERENCES = {
    "default_mode": "minimal",
    "preferred_sounds": [],
    "bedtime_target": "23:00",
    "wake_target": "07:00",
    "breathing_pattern": "4-7-8",
    "persona": None,
    "tracking_level": "basic",
}

DEFAULT_QUOTA = {
    "max_generations": 2,  # free tier
    "generation_count": 0,
    "has_accessed_bucket": False,
}


def upsert_user(uid: str, email: str = "", display_name: str = "",
                picture: str = None) -> dict | None:
    db = get_db()
    if db is None:
        return None
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    db.users.update_one(
        {"_id": uid},
        {
            "$set": {
                "email": email,
                "display_name": display_name,
                "picture": picture,
                "updated_at": now,
            },
            "$setOnInsert": {
                "preferences": dict(DEFAULT_PREFERENCES),
                "tier": {
                    "type": "trial",
                    "trial_started_at": now,
                    "trial_ends_at": now + timedelta(days=7),
                    "generations_per_month": 10,
                    "generations_this_month": 0,
                    "generation_month": now.strftime("%Y-%m"),
                },
                "credits": {"balance": 0, "total_purchased": 0, "total_spent": 0},
                "owned_pack_ids": [],
                "created_at": now,
            },
        },
        upsert=True,
    )
    return get_user(uid)


def get_user(uid: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    return db.users.find_one({"_id": uid})


def update_preferences(uid: str, prefs: dict) -> dict | None:
    db = get_db()
    if db is None:
        return None
    updates = {f"preferences.{k}": v for k, v in prefs.items()}
    updates["updated_at"] = datetime.now(timezone.utc)
    db.users.update_one({"_id": uid}, {"$set": updates})
    return get_user(uid)


def get_user_quota(uid: str) -> dict | None:
    """Get user's generation quota and current count."""
    db = get_db()
    if db is None:
        return None
    user = db.users.find_one({"_id": uid})
    if not user:
        return None
    quota = user.get("quota", dict(DEFAULT_QUOTA))
    return {
        "max_generations": quota.get("max_generations", DEFAULT_QUOTA["max_generations"]),
        "generation_count": quota.get("generation_count", 0),
        "has_accessed_bucket": quota.get("has_accessed_bucket", False),
        "remaining": quota.get("max_generations", 2) - quota.get("generation_count", 0),
        "can_generate": quota.get("generation_count", 0) < quota.get("max_generations", 2),
    }


def increment_generation_count(uid: str) -> bool:
    """Increment the user's generation count. Returns False if quota exceeded."""
    db = get_db()
    if db is None:
        return False
    user = db.users.find_one({"_id": uid})
    if not user:
        return False
    quota = user.get("quota", dict(DEFAULT_QUOTA))
    if quota.get("generation_count", 0) >= quota.get("max_generations", 2):
        return False  # quota exceeded
    db.users.update_one(
        {"_id": uid},
        {
            "$set": {"updated_at": datetime.now(timezone.utc)},
            "$inc": {"quota.generation_count": 1},
        },
    )
    return True


def set_persona(uid: str, persona_key: str | None) -> bool:
    db = get_db()
    if db is None:
        return False
    db.users.update_one(
        {"_id": uid},
        {"$set": {"preferences.persona": persona_key, "updated_at": datetime.now(timezone.utc)}},
    )
    return True


def get_persona(uid: str) -> str | None:
    db = get_db()
    if db is None:
        return None
    user = db.users.find_one({"_id": uid})
    if not user:
        return None
    return user.get("preferences", {}).get("persona")
