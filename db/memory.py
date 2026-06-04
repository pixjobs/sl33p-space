from datetime import datetime, timezone, timedelta

try:
    from bson import ObjectId
except ImportError:
    class ObjectId(str):
        pass

from db import get_db


def add_memory(user_id: str, text: str, kind: str = "outcome", meta: dict = None) -> bool:
    """Store a memory for the agent to recall when building recommendations.

    Args:
        user_id: User ID
        text: Concise memory text (e.g. "Rated 'Ocean Drift' 4/5 when stressed")
        kind: Memory category (outcome, preference, context)
        meta: Optional metadata dict

    Returns:
        True if successful, False if DB unavailable
    """
    db = get_db()
    if db is None:
        return False

    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "text": text[:500],  # Cap memory text
        "kind": kind,
        "meta": meta or {},
        "created_at": now,
        # TTL: 730 days (2 years) from creation
        "expireAt": now + timedelta(days=730),
    }
    db.agent_memory.insert_one(doc)
    return True


def get_memories(user_id: str, limit: int = 5) -> list[dict]:
    """Retrieve recent memories for a user, most recent first.

    Args:
        user_id: User ID
        limit: Max memories to return

    Returns:
        List of {text, kind, created_at} dicts
    """
    db = get_db()
    if db is None:
        return []

    cursor = db.agent_memory.find(
        {"user_id": user_id},
        sort=[("created_at", -1)],
        limit=limit,
    )
    results = []
    for doc in cursor:
        results.append({
            "text": doc.get("text", ""),
            "kind": doc.get("kind", "outcome"),
            "created_at": doc.get("created_at"),
        })
    return results
