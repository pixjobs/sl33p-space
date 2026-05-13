"""
Tier, credit, and subscription management for sl33p-space.

Tier types:
  - free: 2 generations total, basic streaming
  - trial: 7 days full access (auto-set on first login)
  - subscriber: unlimited streaming + N generations/month
  - admin: unlimited everything
"""

from datetime import datetime, timezone, timedelta

from db import get_db


DEFAULT_TIER = {
    "type": "trial",
    "trial_started_at": None,
    "trial_ends_at": None,
    "generations_per_month": 2,
    "generations_this_month": 0,
    "generation_month": None,
}

DEFAULT_CREDITS = {
    "balance": 0,
    "total_purchased": 0,
    "total_spent": 0,
}

TIER_LIMITS = {
    "free": {"generations_per_month": 2, "can_stream": True},
    "trial": {"generations_per_month": 10, "can_stream": True},
    "subscriber": {"generations_per_month": 10, "can_stream": True},
    "admin": {"generations_per_month": 999, "can_stream": True},
}


def get_user_tier(uid: str) -> dict:
    """Get full tier info for a user."""
    db = get_db()
    if db is None:
        return _default_tier_info()

    user = db.users.find_one({"_id": uid})
    if not user:
        return _default_tier_info()

    tier = user.get("tier", dict(DEFAULT_TIER))
    credits = user.get("credits", dict(DEFAULT_CREDITS))

    tier_type = tier.get("type", "free")
    now = datetime.now(timezone.utc)

    # Check if trial is still active
    trial_active = False
    trial_days_remaining = 0
    if tier_type == "trial":
        ends = tier.get("trial_ends_at")
        if ends:
            if ends.tzinfo is None:
                ends = ends.replace(tzinfo=timezone.utc)
            if now < ends:
                trial_active = True
                trial_days_remaining = max(0, (ends - now).days)
            else:
                tier_type = "free"
                db.users.update_one(
                    {"_id": uid},
                    {"$set": {"tier.type": "free"}},
                )

    # Reset monthly counter if month changed
    current_month = now.strftime("%Y-%m")
    if tier.get("generation_month") != current_month:
        db.users.update_one(
            {"_id": uid},
            {"$set": {
                "tier.generations_this_month": 0,
                "tier.generation_month": current_month,
            }},
        )
        tier["generations_this_month"] = 0
        tier["generation_month"] = current_month

    limits = TIER_LIMITS.get(tier_type, TIER_LIMITS["free"])
    gens_remaining = limits["generations_per_month"] - tier.get("generations_this_month", 0)

    can_generate = (
        tier_type == "admin"
        or (trial_active and gens_remaining > 0)
        or (tier_type == "subscriber" and gens_remaining > 0)
        or credits.get("balance", 0) > 0
        or (tier_type == "free" and gens_remaining > 0)
    )

    return {
        "type": tier_type,
        "trial_active": trial_active,
        "trial_days_remaining": trial_days_remaining,
        "generations_per_month": limits["generations_per_month"],
        "generations_this_month": tier.get("generations_this_month", 0),
        "generations_remaining": max(0, gens_remaining),
        "can_generate": can_generate,
        "can_stream": limits["can_stream"],
        "credits_balance": credits.get("balance", 0),
        "owned_packs": user.get("owned_pack_ids", []),
        "is_admin": tier_type == "admin",
    }


def _default_tier_info() -> dict:
    return {
        "type": "free",
        "trial_active": False,
        "trial_days_remaining": 0,
        "generations_per_month": 2,
        "generations_this_month": 0,
        "generations_remaining": 2,
        "can_generate": True,
        "can_stream": True,
        "credits_balance": 0,
        "owned_packs": [],
        "is_admin": False,
    }


def check_generation_allowance(uid: str) -> tuple[bool, str]:
    """Check if user can generate. Returns (allowed, reason)."""
    tier = get_user_tier(uid)

    if tier["is_admin"]:
        return True, "admin"

    if tier["trial_active"] and tier["generations_remaining"] > 0:
        return True, "trial"

    if tier["type"] == "subscriber" and tier["generations_remaining"] > 0:
        return True, "subscription"

    if tier["credits_balance"] > 0:
        return True, "credits"

    if tier["type"] == "free" and tier["generations_remaining"] > 0:
        return True, "free_tier"

    if tier["trial_active"]:
        return False, "Monthly generation limit reached during trial."
    if tier["type"] == "subscriber":
        return False, "Monthly generation limit reached. Use credits for additional generations."

    return False, "Free generations used. Purchase credits or subscribe for more."


def consume_generation(uid: str, source: str = "tier") -> bool:
    """Deduct a generation from the user's allowance."""
    db = get_db()
    if db is None:
        return False

    user = db.users.find_one({"_id": uid})
    if not user:
        return False

    tier = user.get("tier", {})
    if tier.get("type") == "admin":
        return True

    # Try tier allocation first
    if source != "credits":
        limits = TIER_LIMITS.get(tier.get("type", "free"), TIER_LIMITS["free"])
        if tier.get("generations_this_month", 0) < limits["generations_per_month"]:
            db.users.update_one(
                {"_id": uid},
                {"$inc": {"tier.generations_this_month": 1}},
            )
            return True

    # Fall back to credits
    credits = user.get("credits", {})
    if credits.get("balance", 0) > 0:
        db.users.update_one(
            {"_id": uid},
            {
                "$inc": {"credits.balance": -1, "credits.total_spent": 1},
            },
        )
        return True

    return False


def add_credits(uid: str, amount: int, source: str = "purchase") -> int:
    """Add credits to a user's balance. Returns new balance."""
    db = get_db()
    if db is None:
        return 0

    db.users.update_one(
        {"_id": uid},
        {
            "$inc": {
                "credits.balance": amount,
                "credits.total_purchased": amount,
            },
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )
    user = db.users.find_one({"_id": uid})
    return user.get("credits", {}).get("balance", 0) if user else 0


def start_trial(uid: str) -> bool:
    """Start a 7-day trial for a user."""
    db = get_db()
    if db is None:
        return False

    now = datetime.now(timezone.utc)
    db.users.update_one(
        {"_id": uid},
        {"$set": {
            "tier.type": "trial",
            "tier.trial_started_at": now,
            "tier.trial_ends_at": now + timedelta(days=7),
            "tier.generations_per_month": TIER_LIMITS["trial"]["generations_per_month"],
            "updated_at": now,
        }},
    )
    return True


def set_subscription(uid: str, period: str = "monthly") -> bool:
    db = get_db()
    if db is None:
        return False

    now = datetime.now(timezone.utc)
    db.users.update_one(
        {"_id": uid},
        {"$set": {
            "tier.type": "subscriber",
            "tier.subscription_started_at": now,
            "tier.subscription_period": period,
            "tier.generations_per_month": TIER_LIMITS["subscriber"]["generations_per_month"],
            "updated_at": now,
        }},
    )
    return True


def set_admin(uid: str) -> bool:
    db = get_db()
    if db is None:
        return False

    now = datetime.now(timezone.utc)
    db.users.update_one(
        {"_id": uid},
        {"$set": {
            "tier.type": "admin",
            "tier.generations_per_month": TIER_LIMITS["admin"]["generations_per_month"],
            "updated_at": now,
        }},
    )
    return True
