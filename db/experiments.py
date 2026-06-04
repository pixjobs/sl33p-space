"""Multi-night sleep experiments — the coach's agentic core.

The coach forms a hypothesis from the user's own MongoDB history (e.g. "screens
before bed cost you ~1 star"), proposes a short experiment, runs it across nights
as the user reviews each one, then measures the result and reports back. Entirely
deterministic MongoDB work — no music generation, no per-night LLM cost.
"""

from datetime import datetime, timezone, timedelta

try:
    from bson import ObjectId
except ImportError:  # pragma: no cover
    class ObjectId(str):
        pass

from db import get_db

# Lifestyle factors and how the coach phrases avoiding them.
_FACTOR_LABELS = {
    "caffeine": "caffeine",
    "exercise": "exercise",
    "screen_time": "screens before bed",
    "stress": "stress",
    "alcohol": "alcohol",
    "nap": "daytime naps",
    "late_meal": "late meals",
}
# Factors you'd typically ADD rather than avoid — not experiment candidates here.
_GOOD_FACTORS = {"exercise"}


def _round(v):
    return round(v, 1) if isinstance(v, (int, float)) else v


def _factor_baseline(user_id: str, factor: str) -> dict:
    """Average rating on nights WITH vs WITHOUT a factor, from history."""
    out = {"avg_with": None, "avg_without": None, "n_with": 0, "n_without": 0}
    db = get_db()
    if db is None:
        return out
    rows = db.sleep_sessions.aggregate([
        {"$match": {"user_id": user_id,
                    "status": {"$in": ["completed", "reviewed"]},
                    "review.rating": {"$ne": None}}},
        {"$project": {
            "rating": "$review.rating",
            "has": {"$in": [factor, {"$ifNull": ["$review.factors", []]}]},
        }},
        {"$group": {"_id": "$has", "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}},
    ])
    for r in rows:
        if r["_id"]:
            out["avg_with"] = _round(r["avg"])
            out["n_with"] = r["n"]
        else:
            out["avg_without"] = _round(r["avg"])
            out["n_without"] = r["n"]
    return out


def _recently_declined_factors(user_id: str, days: int = 10) -> set:
    db = get_db()
    if db is None:
        return set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.sleep_experiments.find(
        {"user_id": user_id, "status": "declined", "created_at": {"$gte": cutoff}})
    return {r.get("factor") for r in rows}


def get_active_experiment(user_id: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    doc = db.sleep_experiments.find_one(
        {"user_id": user_id, "status": "active"}, sort=[("created_at", -1)])
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def get_recent_completed_experiment(user_id: str) -> dict | None:
    """A completed experiment the user hasn't acknowledged yet (to report once)."""
    db = get_db()
    if db is None:
        return None
    doc = db.sleep_experiments.find_one(
        {"user_id": user_id, "status": "completed", "acknowledged": {"$ne": True}},
        sort=[("updated_at", -1)])
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def propose_experiment(user_id: str, insights: dict = None) -> dict | None:
    """Suggest a data-grounded N-night experiment, or None if not warranted.

    Picks the lifestyle factor most associated with worse nights, provided there
    is enough history and it isn't already being tested or recently declined.
    """
    if get_active_experiment(user_id):
        return None
    if insights is None:
        from db.insights import get_user_sleep_insights
        insights = get_user_sleep_insights(user_id)

    stats = insights.get("stats") or {}
    overall = stats.get("avg_rating")
    if not overall or (stats.get("reviewed_sessions") or 0) < 3:
        return None

    declined = _recently_declined_factors(user_id)
    candidate = None
    for row in sorted(insights.get("factor_correlations") or [],
                      key=lambda r: r.get("avg_rating") or 5):
        f = row.get("factor")
        if not f or f in declined or f in _GOOD_FACTORS:
            continue
        if (row.get("sessions") or 0) < 2:
            continue
        if (row.get("avg_rating") or 5) >= overall - 0.3:
            continue  # not clearly dragging things down
        candidate = row
        break
    if not candidate:
        return None

    factor = candidate["factor"]
    label = _FACTOR_LABELS.get(factor, factor.replace("_", " "))
    baseline = _factor_baseline(user_id, factor)
    detail = None
    if baseline["avg_with"] is not None and baseline["avg_without"] is not None:
        detail = (f"On {label} nights you average {baseline['avg_with']}/5, "
                  f"versus {baseline['avg_without']}/5 without.")
    return {
        "factor": factor,
        "label": label,
        "direction": "avoid",
        "hypothesis": f"Cutting {label} might lift your sleep",
        "detail": detail,
        "target_nights": 3,
        "baseline": baseline,
        "status": "proposed",
    }


def accept_experiment(user_id: str, factor: str, target_nights: int = 3) -> dict | None:
    """Start an active experiment for a factor (idempotent if one is running)."""
    db = get_db()
    if db is None:
        return None
    existing = get_active_experiment(user_id)
    if existing:
        return existing
    label = _FACTOR_LABELS.get(factor, factor.replace("_", " "))
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "factor": factor,
        "label": label,
        "direction": "avoid",
        "hypothesis": f"Cutting {label} might lift your sleep",
        "target_nights": int(target_nights),
        "baseline": _factor_baseline(user_id, factor),
        "status": "active",
        "nights": [],
        "created_at": now,
        "updated_at": now,
        "expireAt": now + timedelta(days=60),
    }
    res = db.sleep_experiments.insert_one(doc)
    doc["_id"] = str(res.inserted_id)
    return doc


def decline_experiment(user_id: str, factor: str) -> bool:
    """Record a decline so the coach won't re-propose the same factor for a while."""
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    db.sleep_experiments.insert_one({
        "user_id": user_id,
        "factor": factor,
        "status": "declined",
        "created_at": now,
        "updated_at": now,
        "expireAt": now + timedelta(days=30),
    })
    return True


def acknowledge_experiment(user_id: str, exp_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    db.sleep_experiments.update_one(
        {"_id": ObjectId(exp_id), "user_id": user_id},
        {"$set": {"acknowledged": True, "updated_at": datetime.now(timezone.utc)}})
    return True


def _finalize(exp: dict, nights: list) -> dict:
    """Compare adhered nights against control nights (or the historical baseline)."""
    adhered = [n["rating"] for n in nights if n.get("adhered") and n.get("rating") is not None]
    control = [n["rating"] for n in nights if not n.get("adhered") and n.get("rating") is not None]
    baseline = exp.get("baseline") or {}
    adhered_avg = _round(sum(adhered) / len(adhered)) if adhered else None
    control_avg = (_round(sum(control) / len(control)) if control
                   else baseline.get("avg_with"))
    label = exp.get("label") or exp.get("factor")
    delta = None
    if adhered_avg is not None and control_avg is not None:
        delta = _round(adhered_avg - control_avg)

    if delta is None:
        conclusion = f"Tried cutting {label} for {len(adhered)} nights — not enough to compare yet."
    elif delta >= 0.5:
        conclusion = (f"Cutting {label} helped — {adhered_avg}/5 versus {control_avg}/5. "
                      f"Worth keeping up.")
    elif delta <= -0.5:
        conclusion = f"Cutting {label} didn't help this time ({adhered_avg}/5 versus {control_avg}/5)."
    else:
        conclusion = f"Cutting {label} made little difference ({adhered_avg}/5 versus {control_avg}/5)."
    return {
        "adhered_avg": adhered_avg,
        "control_avg": control_avg,
        "delta": delta,
        "adhered_nights": len(adhered),
        "conclusion": conclusion,
    }


def record_experiment_night(user_id: str, session: dict) -> None:
    """On each reviewed night, log adherence + rating against any active experiment.
    Completes the experiment once enough adhered nights are collected."""
    db = get_db()
    if db is None:
        return
    exp = db.sleep_experiments.find_one(
        {"user_id": user_id, "status": "active"}, sort=[("created_at", -1)])
    if not exp:
        return

    factor = exp["factor"]
    direction = exp.get("direction", "avoid")
    review = session.get("review") or {}
    rating = review.get("rating")
    present = factor in (review.get("factors") or [])
    adhered = (not present) if direction == "avoid" else present

    sid = str(session.get("_id"))
    nights = exp.get("nights") or []
    if any(n.get("session_id") == sid for n in nights):
        return  # idempotent on re-review

    nights.append({
        "session_id": sid,
        "date": datetime.now(timezone.utc),
        "adhered": adhered,
        "rating": rating,
    })
    update = {"nights": nights, "updated_at": datetime.now(timezone.utc)}

    adhered_count = sum(1 for n in nights if n.get("adhered"))
    if adhered_count >= exp.get("target_nights", 3):
        update["status"] = "completed"
        update["result"] = _finalize(exp, nights)

    db.sleep_experiments.update_one({"_id": exp["_id"]}, {"$set": update})
