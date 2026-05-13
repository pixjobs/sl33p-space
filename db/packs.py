"""
Music packs — curated bundles of tracks users can purchase with credits.
"""

from datetime import datetime, timezone

from bson import ObjectId

from db import get_db


def get_all_packs(available_only: bool = True) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    query = {"available": True} if available_only else {}
    cursor = db.packs.find(query, sort=[("featured", -1), ("created_at", -1)])
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["track_ids"] = [str(tid) for tid in doc.get("track_ids", [])]
        results.append(doc)
    return results


def get_pack(pack_id_or_slug: str) -> dict | None:
    db = get_db()
    if db is None:
        return None

    try:
        doc = db.packs.find_one({"_id": ObjectId(pack_id_or_slug)})
    except Exception:
        doc = db.packs.find_one({"slug": pack_id_or_slug})

    if doc:
        doc["_id"] = str(doc["_id"])
        doc["track_ids"] = [str(tid) for tid in doc.get("track_ids", [])]
    return doc


def create_pack(name: str, slug: str, description: str,
                track_ids: list[str], price_credits: int = 5,
                category: str = "general") -> str | None:
    db = get_db()
    if db is None:
        return None

    now = datetime.now(timezone.utc)
    doc = {
        "slug": slug,
        "name": name,
        "description": description,
        "track_ids": [ObjectId(tid) if not isinstance(tid, ObjectId) else tid for tid in track_ids],
        "price_credits": price_credits,
        "category": category,
        "featured": False,
        "available": True,
        "created_at": now,
    }
    result = db.packs.insert_one(doc)
    return str(result.inserted_id)


def user_owns_pack(uid: str, pack_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    user = db.users.find_one({"_id": uid})
    if not user:
        return False
    owned = user.get("owned_pack_ids", [])
    return pack_id in [str(p) for p in owned]


def purchase_pack(uid: str, pack_slug: str) -> dict:
    """Purchase a pack with credits. Returns pack info or error."""
    db = get_db()
    if db is None:
        return {"error": "Database not available"}

    pack = get_pack(pack_slug)
    if not pack:
        return {"error": f"Pack '{pack_slug}' not found"}

    pack_id = pack["_id"]
    if user_owns_pack(uid, pack_id):
        return {"error": "You already own this pack"}

    user = db.users.find_one({"_id": uid})
    if not user:
        return {"error": "User not found"}

    # Admin gets packs for free
    tier_type = user.get("tier", {}).get("type", "free")
    cost = pack.get("price_credits", 5)

    if tier_type != "admin":
        balance = user.get("credits", {}).get("balance", 0)
        if balance < cost:
            return {"error": f"Not enough credits. Need {cost}, have {balance}."}

        db.users.update_one(
            {"_id": uid},
            {"$inc": {"credits.balance": -cost, "credits.total_spent": cost}},
        )

    db.users.update_one(
        {"_id": uid},
        {
            "$addToSet": {"owned_pack_ids": pack_id},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )

    return {
        "purchased": True,
        "pack": pack["name"],
        "cost": cost if tier_type != "admin" else 0,
        "tracks": len(pack.get("track_ids", [])),
    }
