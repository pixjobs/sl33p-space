from datetime import datetime, timezone

from db import get_db

DEFAULT_PREFERENCES = {
    "default_mode": "minimal",
    "preferred_sounds": [],
    "bedtime_target": "23:00",
    "wake_target": "07:00",
    "breathing_pattern": "4-7-8",
}


def upsert_user(uid: str, email: str = "", display_name: str = "",
                picture: str = None) -> dict | None:
    db = get_db()
    if db is None:
        return None
    now = datetime.now(timezone.utc)
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
