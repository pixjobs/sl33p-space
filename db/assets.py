import random
from datetime import datetime, timezone

from db import get_db


def cache_apod(date_str: str, url: str, hdurl: str = "", title: str = "",
               explanation: str = "", media_type: str = "image") -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    db.generated_assets.update_one(
        {"type": "apod", "apod_date": date_str},
        {
            "$set": {
                "url": url,
                "hdurl": hdurl or url,
                "title": title,
                "explanation": explanation,
                "media_type": media_type,
                "source": "nasa",
                "last_used_at": now,
            },
            "$inc": {"use_count": 1},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return True


def get_cached_apod(date_str: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    return db.generated_assets.find_one({"type": "apod", "apod_date": date_str})


def get_latest_apod() -> dict | None:
    db = get_db()
    if db is None:
        return None
    return db.generated_assets.find_one(
        {"type": "apod", "media_type": "image"},
        sort=[("apod_date", -1)],
    )


def cache_scene_image(theme: str, storage_path: str, prompt: str = "",
                       title: str = "") -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    db.generated_assets.insert_one({
        "type": "scene_image",
        "source": "gemini-flash",
        "theme": theme,
        "prompt": prompt,
        "title": title,
        "storage_path": storage_path,
        "use_count": 0,
        "created_at": now,
        "last_used_at": None,
    })
    return True


def get_random_scene(theme: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    scenes = list(db.generated_assets.find({"type": "scene_image", "theme": theme}))
    if not scenes:
        return None
    scene = random.choice(scenes)
    db.generated_assets.update_one(
        {"_id": scene["_id"]},
        {"$set": {"last_used_at": datetime.now(timezone.utc)},
         "$inc": {"use_count": 1}},
    )
    scene["_id"] = str(scene["_id"])
    return scene


def get_scene_pool_size(theme: str) -> int:
    db = get_db()
    if db is None:
        return 0
    return db.generated_assets.count_documents({"type": "scene_image", "theme": theme})
