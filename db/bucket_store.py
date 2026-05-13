"""
Bucket store — curated library of pre-generated content.

Users get 2 free custom generations, then access the bucket store
instead of generating new content.

The bucket store contains:
- NASA APOD images (daily space photos with mood tags)
- Pre-generated Lyria tracks (NASA-themed)
- Gemini scene images (curated themes)
"""

import random
from datetime import datetime, timezone

from db import get_db
from db.assets import get_apod_pool, get_latest_apod, get_cached_apod


def get_bucket_items(user_id: str, category: str = None, limit: int = 12) -> list[dict]:
    """Get items from the bucket store for a user."""
    db = get_db()
    if db is None:
        return []

    user = db.users.find_one(
        {"_id": user_id},
        {"bucket_store": 1},
    )
    if user and "bucket_store" in user:
        items = user["bucket_store"]
        if category:
            items = [i for i in items if i.get("category") == category]
        return items[:limit]

    # Fallback: generate bucket from existing data
    return _build_fallback_bucket(category, limit)


def _build_fallback_bucket(category: str = None, limit: int = 12) -> list[dict]:
    """Build bucket items from existing APOD + generated assets."""
    items = []

    # Add APOD images
    if not category or category == "space":
        apod_pool = get_apod_pool(limit=20)
        for apod in apod_pool[:8]:
            items.append({
                "id": f"apod-{apod['date']}",
                "title": apod["title"],
                "description": apod.get("explanation", "")[:100] + "..." if apod.get("explanation") else "",
                "url": apod["url"],
                "category": "space",
                "type": "image",
                "date": apod["date"],
            })

    # Add scene images
    if not category or category == "scenes":
        db = get_db()
        if db:
            scenes = list(db.generated_assets.find(
                {"type": "scene_image", "available": {"$ne": False}},
                limit=limit,
            ))
            for scene in scenes:
                items.append({
                    "id": str(scene["_id"]),
                    "title": scene.get("title", "Scene"),
                    "description": scene.get("prompt", "")[:100],
                    "url": scene.get("storage_path", ""),
                    "category": "scenes",
                    "theme": scene.get("theme", "default"),
                    "type": "image",
                })

    return items[:limit]


def get_bucket_stats(user_id: str) -> dict:
    """Get bucket store statistics for a user."""
    db = get_db()
    if db is None:
        return {"total_items": 0, "categories": {}}

    bucket = db.users.find_one({"_id": user_id}, {"bucket_store": 1})
    items = bucket.get("bucket_store", []) if bucket else []

    categories = {}
    for item in items:
        cat = item.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "total_items": len(items),
        "categories": categories,
        "last_updated": items[0].get("updated_at") if items else None,
    }


def sync_bucket_to_user(user_id: str) -> int:
    """Sync the global bucket store to a user's bucket store.
    
    Returns the number of new items added.
    """
    db = get_db()
    if db is None:
        return 0

    now = datetime.now(timezone.utc)
    
    # Build items from APOD and scenes
    items = []
    
    # Add APOD images
    apod_pool = get_apod_pool(limit=30)
    for apod in apod_pool:
        items.append({
            "id": f"apod-{apod['date']}",
            "title": apod["title"],
            "description": apod.get("explanation", "")[:100] + "..." if apod.get("explanation") else "",
            "url": apod["url"],
            "category": "space",
            "type": "image",
            "date": apod["date"],
            "available": True,
            "created_at": now,
        })

    # Add scene images
    scenes = list(db.generated_assets.find(
        {"type": "scene_image", "available": {"$ne": False}},
        limit=20,
    ))
    for scene in scenes:
        items.append({
            "id": str(scene["_id"]),
            "title": scene.get("title", "Scene"),
            "description": scene.get("prompt", "")[:100],
            "url": scene.get("storage_path", ""),
            "category": "scenes",
            "theme": scene.get("theme", "default"),
            "type": "image",
            "available": True,
            "created_at": now,
        })

    # Update user's bucket store
    db.users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "bucket_store": items,
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )

    return len(items)
