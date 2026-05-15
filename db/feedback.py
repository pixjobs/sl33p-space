from datetime import datetime, timezone

from db import get_db

VALID_TYPES = {"thumbs_up", "thumbs_down", "bug", "idea", "other"}


def submit_feedback(user_id: str, feedback_type: str,
                    message: str = "", context: dict = None) -> str | None:
    db = get_db()
    if db is None:
        return None
    if feedback_type not in VALID_TYPES:
        return None
    doc = {
        "user_id": user_id,
        "type": feedback_type,
        "message": message[:2000] if message else "",
        "context": context or {},
        "created_at": datetime.now(timezone.utc),
    }
    result = db.feedback.insert_one(doc)
    return str(result.inserted_id)


def get_recent_feedback(limit: int = 50) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    cursor = db.feedback.find(
        sort=[("created_at", -1)],
        limit=limit,
    )
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


def get_user_feedback_summary(user_id: str, limit: int = 10) -> dict:
    db = get_db()
    if db is None:
        return {"items": [], "counts": {}}
    cursor = db.feedback.find(
        {"user_id": user_id},
        sort=[("created_at", -1)],
        limit=limit,
    )
    items = []
    for doc in cursor:
        items.append({
            "type": doc.get("type"),
            "message": doc.get("message", ""),
            "context": doc.get("context", {}),
            "created_at": doc.get("created_at"),
        })

    counts_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
    ]
    counts = {}
    for row in db.feedback.aggregate(counts_pipeline):
        counts[row["_id"]] = row["count"]

    return {"items": items, "counts": counts}
