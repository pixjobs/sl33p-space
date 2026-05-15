import hashlib
from datetime import datetime, timezone, timedelta

from db import get_db

ADMIN_EMAILS = {"hello@pixjobs.com"}

_ADJECTIVES = [
    "Cosmic", "Lunar", "Stellar", "Nebula", "Orbit", "Solar",
    "Astral", "Comet", "Nova", "Quasar", "Pulsar", "Twilight",
    "Aurora", "Void", "Drift", "Haze", "Frost", "Velvet",
    "Ember", "Crystal", "Silent", "Misty", "Dusk", "Echo",
]
_NOUNS = [
    "Penguin", "Fox", "Owl", "Moth", "Whale", "Heron",
    "Otter", "Lynx", "Raven", "Falcon", "Firefly", "Panda",
    "Badger", "Dolphin", "Koala", "Sparrow", "Tortoise", "Gecko",
    "Hummingbird", "Elk", "Manta", "Ibis", "Crane", "Seal",
]


def _pseudonymise_email(email: str) -> str:
    if not email:
        return "—"
    if email in ADMIN_EMAILS:
        return email
    h = int(hashlib.sha256(email.encode()).hexdigest(), 16)
    adj = _ADJECTIVES[h % len(_ADJECTIVES)]
    noun = _NOUNS[(h // len(_ADJECTIVES)) % len(_NOUNS)]
    return f"{adj} {noun}"


def get_platform_stats() -> dict:
    db = get_db()
    if db is None:
        return _empty_stats()

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_users = db.users.count_documents({})
    active_users = db.users.count_documents({"updated_at": {"$gte": week_ago}})
    total_sessions = db.sleep_sessions.count_documents({})
    reviewed_sessions = db.sleep_sessions.count_documents({"status": "reviewed"})

    track_count = db.tracks.count_documents({"archived": {"$ne": True}})

    cost_rows = list(db.api_usage.aggregate([
        {"$match": {"created_at": {"$gte": month_ago}}},
        {"$group": {
            "_id": "$service",
            "calls": {"$sum": 1},
            "cost": {"$sum": "$estimated_cost_usd"},
        }},
    ]))
    total_cost = sum(r.get("cost", 0) for r in cost_rows)
    cost_by_service = {r["_id"]: {"calls": r["calls"], "cost": round(r["cost"], 4)}
                       for r in cost_rows}

    return {
        "total_users": total_users,
        "active_users_7d": active_users,
        "total_sessions": total_sessions,
        "reviewed_sessions": reviewed_sessions,
        "total_tracks": track_count,
        "estimated_cost_30d": round(total_cost, 4),
        "cost_by_service": cost_by_service,
    }


def get_user_list(page: int = 1, per_page: int = 50) -> dict:
    db = get_db()
    if db is None:
        return {"users": [], "total": 0, "page": page, "per_page": per_page}

    total = db.users.count_documents({})
    skip = (page - 1) * per_page

    users = list(db.users.find(
        {},
        sort=[("updated_at", -1)],
        skip=skip,
        limit=per_page,
    ))

    month_ago = datetime.now(timezone.utc) - timedelta(days=30)

    result = []
    for u in users:
        uid = u["_id"]
        session_count = db.sleep_sessions.count_documents({"user_id": uid})
        tier = u.get("tier", {})

        usage_rows = list(db.api_usage.aggregate([
            {"$match": {"user_id": uid, "created_at": {"$gte": month_ago}}},
            {"$group": {
                "_id": None,
                "calls": {"$sum": 1},
                "cost": {"$sum": "$estimated_cost_usd"},
            }},
        ]))
        usage = usage_rows[0] if usage_rows else {}

        email = u.get("email", "")
        email_hint = (email[:7] + "...") if len(email) > 7 else email

        credits = u.get("credits", {})

        result.append({
            "uid": uid,
            "email": _pseudonymise_email(email),
            "email_hint": email_hint,
            "display_name": u.get("display_name", ""),
            "tier": tier.get("type", "free"),
            "generations_this_month": tier.get("generations_this_month", 0),
            "credits_balance": credits.get("balance", 0),
            "session_count": session_count,
            "timezone": u.get("timezone", ""),
            "last_active": u.get("updated_at").isoformat() if u.get("updated_at") else "",
            "created_at": u.get("created_at").isoformat() if u.get("created_at") else "",
            "api_calls_30d": usage.get("calls", 0),
            "api_cost_30d": round(usage.get("cost", 0), 4),
        })

    return {"users": result, "total": total, "page": page, "per_page": per_page}


def get_usage_summary(days: int = 30) -> dict:
    db = get_db()
    if db is None:
        return {"daily": [], "total_calls": 0, "total_cost": 0}

    since = datetime.now(timezone.utc) - timedelta(days=days)

    daily_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": {
                "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "service": "$service",
            },
            "calls": {"$sum": 1},
            "cost": {"$sum": "$estimated_cost_usd"},
        }},
        {"$sort": {"_id.date": 1}},
    ]
    rows = list(db.api_usage.aggregate(daily_pipeline))

    daily = {}
    total_calls = 0
    total_cost = 0.0
    for row in rows:
        d = row["_id"]["date"]
        svc = row["_id"]["service"]
        if d not in daily:
            daily[d] = {"date": d, "lyria_calls": 0, "gemini_calls": 0, "cost": 0}
        if svc == "lyria":
            daily[d]["lyria_calls"] += row["calls"]
        else:
            daily[d]["gemini_calls"] += row["calls"]
        daily[d]["cost"] = round(daily[d]["cost"] + row["cost"], 4)
        total_calls += row["calls"]
        total_cost += row["cost"]

    return {
        "daily": list(daily.values()),
        "total_calls": total_calls,
        "total_cost": round(total_cost, 4),
    }


def get_track_list(page: int = 1, per_page: int = 20) -> dict:
    db = get_db()
    if db is None:
        return {"tracks": [], "total": 0, "page": page, "pages": 0}

    total = db.tracks.count_documents({})
    pages = max(1, -(-total // per_page))
    page = max(1, min(page, pages))
    skip = (page - 1) * per_page

    tracks = list(db.tracks.find({}, sort=[("created_at", -1)], skip=skip, limit=per_page))

    uid_set = {t.get("generated_by", "system") for t in tracks} - {"system"}
    uid_to_email = {}
    if uid_set:
        users = db.users.find({"_id": {"$in": list(uid_set)}}, {"email": 1})
        uid_to_email = {u["_id"]: u.get("email", "") for u in users}

    from db.tracks import resolve_track_url
    result = []
    for t in tracks:
        uid = t.get("generated_by", "system")
        if uid == "system":
            creator = "System"
        else:
            creator = _pseudonymise_email(uid_to_email.get(uid, ""))

        result.append({
            "title": t.get("title", ""),
            "prompt": t.get("prompt", ""),
            "model": t.get("model", ""),
            "mood_tags": t.get("mood_tags", []),
            "energy_level": t.get("energy_level", "low"),
            "size_kb": t.get("size_kb", 0),
            "src": resolve_track_url(t),
            "created_by": creator,
            "is_preset": t.get("is_preset", False),
            "archived": t.get("archived", False),
            "created_at": t.get("created_at").isoformat() if t.get("created_at") else "",
        })

    return {"tracks": result, "total": total, "page": page, "pages": pages}


def _empty_stats() -> dict:
    return {
        "total_users": 0,
        "active_users_7d": 0,
        "total_sessions": 0,
        "reviewed_sessions": 0,
        "total_tracks": 0,
        "estimated_cost_30d": 0,
        "cost_by_service": {},
    }
