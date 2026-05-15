from datetime import datetime, timezone, timedelta

from db import get_db


def log_api_usage(user_id: str, service: str, model: str,
                  input_tokens: int = 0, output_tokens: int = 0,
                  duration_s: float = 0, cost_usd: float = 0,
                  metadata: dict = None):
    db = get_db()
    if db is None:
        return
    db.api_usage.insert_one({
        "user_id": user_id,
        "service": service,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_s": round(duration_s, 2),
        "estimated_cost_usd": round(cost_usd, 6),
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc),
    })


def get_user_usage(user_id: str, days: int = 30) -> dict:
    db = get_db()
    if db is None:
        return {"total_calls": 0, "total_cost": 0, "by_service": {}}

    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"user_id": user_id, "created_at": {"$gte": since}}},
        {"$group": {
            "_id": "$service",
            "calls": {"$sum": 1},
            "cost": {"$sum": "$estimated_cost_usd"},
            "total_duration": {"$sum": "$duration_s"},
        }},
    ]
    rows = list(db.api_usage.aggregate(pipeline))
    by_service = {}
    total_calls = 0
    total_cost = 0.0
    for row in rows:
        svc = row["_id"]
        by_service[svc] = {
            "calls": row["calls"],
            "cost": round(row["cost"], 4),
            "duration_s": round(row["total_duration"], 1),
        }
        total_calls += row["calls"]
        total_cost += row["cost"]

    return {
        "total_calls": total_calls,
        "total_cost": round(total_cost, 4),
        "by_service": by_service,
    }


def get_global_usage(days: int = 30) -> dict:
    db = get_db()
    if db is None:
        return {"total_calls": 0, "total_cost": 0, "daily": [], "per_user": []}

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
    daily_rows = list(db.api_usage.aggregate(daily_pipeline))
    daily = {}
    for row in daily_rows:
        d = row["_id"]["date"]
        if d not in daily:
            daily[d] = {"date": d, "calls": 0, "cost": 0}
        daily[d]["calls"] += row["calls"]
        daily[d]["cost"] = round(daily[d]["cost"] + row["cost"], 4)

    user_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": "$user_id",
            "calls": {"$sum": 1},
            "cost": {"$sum": "$estimated_cost_usd"},
        }},
        {"$sort": {"cost": -1}},
        {"$limit": 50},
    ]
    user_rows = list(db.api_usage.aggregate(user_pipeline))

    totals_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": None,
            "calls": {"$sum": 1},
            "cost": {"$sum": "$estimated_cost_usd"},
        }},
    ]
    totals = list(db.api_usage.aggregate(totals_pipeline))
    t = totals[0] if totals else {}

    return {
        "total_calls": t.get("calls", 0),
        "total_cost": round(t.get("cost", 0), 4),
        "daily": list(daily.values()),
        "per_user": [
            {"user_id": r["_id"], "calls": r["calls"], "cost": round(r["cost"], 4)}
            for r in user_rows
        ],
    }
