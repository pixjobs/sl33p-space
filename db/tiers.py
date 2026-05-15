"""
Tier and credit management for sl33p-space.

Tier types:
  - free: 2 generations/month, full streaming
  - admin: unlimited everything
  - Credits: per-generation top-up (monetisation placeholder)
"""

from datetime import datetime, timezone

from db import get_db


TIER_LIMITS = {
    "free": {"generations_per_month": 2, "chat_per_day": 10},
    "plus": {"generations_per_month": 10, "chat_per_day": 50},
    "admin": {"generations_per_month": 999, "chat_per_day": 999},
}


def get_user_tier(uid: str) -> dict:
    db = get_db()
    if db is None:
        return _default_tier_info()

    user = db.users.find_one({"_id": uid})
    if not user:
        return _default_tier_info()

    tier = user.get("tier", {})
    credits = user.get("credits", {"balance": 0})
    tier_type = tier.get("type", "free")

    # Migrate legacy trial users to free
    if tier_type == "trial":
        tier_type = "free"
        db.users.update_one({"_id": uid}, {"$set": {"tier.type": "free"}})

    # Migrate legacy subscriber users to free (no billing yet)
    if tier_type == "subscriber":
        tier_type = "free"
        db.users.update_one({"_id": uid}, {"$set": {"tier.type": "free"}})

    now = datetime.now(timezone.utc)

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

    limits = TIER_LIMITS.get(tier_type, TIER_LIMITS["free"])
    gens_used = tier.get("generations_this_month", 0)
    gens_remaining = max(0, limits["generations_per_month"] - gens_used)
    credit_balance = credits.get("balance", 0)

    can_generate = (
        tier_type == "admin"
        or gens_remaining > 0
        or credit_balance > 0
    )

    chat_bonus = user.get("chat_bonus", 0) if user else 0

    return {
        "type": tier_type,
        "generations_per_month": limits["generations_per_month"],
        "generations_this_month": gens_used,
        "generations_remaining": gens_remaining,
        "can_generate": can_generate,
        "credits_balance": credit_balance,
        "is_admin": tier_type == "admin",
        "chat_per_day": limits.get("chat_per_day", 10),
        "chat_bonus": chat_bonus,
    }


def _default_tier_info() -> dict:
    return {
        "type": "free",
        "generations_per_month": 2,
        "generations_this_month": 0,
        "generations_remaining": 2,
        "can_generate": True,
        "credits_balance": 0,
        "is_admin": False,
        "chat_per_day": 10,
        "chat_bonus": 0,
    }


def check_generation_allowance(uid: str) -> tuple[bool, str]:
    tier = get_user_tier(uid)

    if tier["is_admin"]:
        return True, "admin"

    if tier["generations_remaining"] > 0:
        return True, "free_tier"

    if tier["credits_balance"] > 0:
        return True, "credits"

    return False, "Free generations used. Purchase credits for more."


def consume_generation(uid: str, source: str = "tier") -> bool:
    db = get_db()
    if db is None:
        return False

    user = db.users.find_one({"_id": uid})
    if not user:
        return False

    tier = user.get("tier", {})
    if tier.get("type") == "admin":
        return True

    # Try free tier allocation first
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
            {"$inc": {"credits.balance": -1, "credits.total_spent": 1}},
        )
        return True

    return False


def add_credits(uid: str, amount: int, source: str = "purchase") -> int:
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


def gift_credits(from_uid: str, to_uid: str, amount: int,
                 from_name: str = "") -> int:
    db = get_db()
    if db is None:
        return 0

    new_balance = add_credits(to_uid, amount, source="gift")

    if from_uid != to_uid:
        db.credit_gifts.insert_one({
            "from_uid": from_uid,
            "to_uid": to_uid,
            "from_name": from_name,
            "amount": amount,
            "source": "admin",
            "seen": False,
            "created_at": datetime.now(timezone.utc),
        })

    return new_balance


def get_pending_gifts(uid: str) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    cursor = db.credit_gifts.find(
        {"to_uid": uid, "seen": False},
        sort=[("created_at", -1)],
    )
    results = []
    for doc in cursor:
        results.append({
            "from_name": doc.get("from_name", "Someone"),
            "amount": doc.get("amount", 0),
            "source": doc.get("source", "admin"),
        })
    return results


def mark_gifts_seen(uid: str) -> bool:
    db = get_db()
    if db is None:
        return False
    db.credit_gifts.update_many(
        {"to_uid": uid, "seen": False},
        {"$set": {"seen": True}},
    )
    return True


MAX_REFERRAL_CREDITS = 5


def get_referral_code(uid: str) -> str | None:
    db = get_db()
    if db is None:
        return None
    user = db.users.find_one({"_id": uid})
    if not user:
        return None
    code = user.get("referral_code")
    if not code:
        import hashlib
        code = hashlib.sha256(uid.encode()).hexdigest()[:8]
        db.users.update_one({"_id": uid}, {"$set": {"referral_code": code}})
    return code


def get_referral_stats(uid: str) -> dict:
    db = get_db()
    if db is None:
        return {"code": None, "referrals_given": 0, "credits_earned": 0}
    user = db.users.find_one({"_id": uid})
    if not user:
        return {"code": None, "referrals_given": 0, "credits_earned": 0}
    return {
        "code": user.get("referral_code"),
        "referrals_given": user.get("referrals_given", 0),
        "credits_earned": user.get("referrals_given", 0),
        "max_referrals": MAX_REFERRAL_CREDITS,
    }


def redeem_referral(code: str, new_uid: str) -> tuple[bool, str]:
    db = get_db()
    if db is None:
        return False, "Database unavailable"

    referrer = db.users.find_one({"referral_code": code})
    if not referrer:
        return False, "Invalid referral code"

    referrer_uid = referrer["_id"]

    if referrer_uid == new_uid:
        return False, "Cannot use your own referral code"

    new_user = db.users.find_one({"_id": new_uid})
    if not new_user:
        return False, "User not found"

    if new_user.get("referred_by"):
        return False, "Already redeemed a referral"

    if referrer.get("referrals_given", 0) >= MAX_REFERRAL_CREDITS:
        return False, "Referrer has reached the referral limit"

    now = datetime.now(timezone.utc)
    referrer_name = referrer.get("display_name", "").split()[0] or "A friend"
    new_user_name = new_user.get("display_name", "").split()[0] or "A friend"

    add_credits(referrer_uid, 1, source="referral")
    add_credits(new_uid, 1, source="referral")

    db.users.update_one(
        {"_id": new_uid},
        {"$set": {"referred_by": referrer_uid, "updated_at": now}},
    )
    db.users.update_one(
        {"_id": referrer_uid},
        {"$inc": {"referrals_given": 1}, "$set": {"updated_at": now}},
    )

    db.credit_gifts.insert_many([
        {
            "from_uid": referrer_uid,
            "to_uid": new_uid,
            "from_name": referrer_name,
            "amount": 1,
            "source": "referral",
            "seen": False,
            "created_at": now,
        },
        {
            "from_uid": new_uid,
            "to_uid": referrer_uid,
            "from_name": new_user_name,
            "amount": 1,
            "source": "referral",
            "seen": False,
            "created_at": now,
        },
    ])

    return True, "ok"


def set_admin(uid: str) -> bool:
    db = get_db()
    if db is None:
        return False

    db.users.update_one(
        {"_id": uid},
        {"$set": {
            "tier.type": "admin",
            "tier.generations_per_month": TIER_LIMITS["admin"]["generations_per_month"],
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return True


def set_user_tier(uid: str, tier_type: str) -> bool:
    db = get_db()
    if db is None:
        return False
    if tier_type not in TIER_LIMITS:
        return False
    limits = TIER_LIMITS[tier_type]
    db.users.update_one(
        {"_id": uid},
        {"$set": {
            "tier.type": tier_type,
            "tier.generations_per_month": limits["generations_per_month"],
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return True


def check_chat_allowance(uid: str) -> tuple[bool, int, int]:
    db = get_db()
    if db is None:
        return True, 999, 999

    user = db.users.find_one({"_id": uid})
    tier_type = "free"
    chat_bonus = 0
    if user:
        tier_type = user.get("tier", {}).get("type", "free")
        chat_bonus = user.get("chat_bonus", 0)

    if tier_type == "admin":
        return True, 999, 999

    limits = TIER_LIMITS.get(tier_type, TIER_LIMITS["free"])
    daily_limit = limits.get("chat_per_day", 10)
    total_limit = daily_limit + chat_bonus

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    used_today = db.api_usage.count_documents({
        "user_id": uid,
        "metadata.purpose": "chat",
        "created_at": {"$gte": today_start},
    })

    remaining = max(0, total_limit - used_today)
    return remaining > 0, remaining, total_limit


def award_sleep_bonus(uid: str, duration_minutes: int) -> int:
    if duration_minutes < 30:
        return 0
    db = get_db()
    if db is None:
        return 0
    bonus = min(duration_minutes // 60, 5)
    if bonus <= 0:
        return 0
    db.users.update_one(
        {"_id": uid},
        {
            "$inc": {"chat_bonus": bonus},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )
    return bonus
