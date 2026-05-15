"""
Playlist builder for sl33p-space.

Builds mood-aware, persona-adapted playlists with a settling -> deep_sleep arc.
Uses sleep history to learn what works for each user.
"""

from datetime import datetime, timezone

from bson import ObjectId

from db import get_db
from db.tracks import get_all_tracks, resolve_track_url


PERSONA_BOOSTS = {
    "shift_worker": {"tired": 0.1, "calm": 0.05},
    "emergency_services": {"stressed": 0.15, "calm": 0.1},
    "shallow_sleeper": {"calm": 0.15, "tired": 0.1},
    "insomniac": {"restless": 0.1, "calm": 0.15, "stressed": 0.1},
}

ENERGY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_playlist(mood: str, persona: str | None, user_id: str,
                   session_id: str | None = None,
                   max_tracks: int = 10) -> dict | None:
    """Build a mood-aware playlist for a sleep session.

    Returns:
        {
            "playlist_id": "...",
            "tracks": [{"track_id": ..., "title": ..., "src": ..., "role": ..., "order": ..., "score": ...}],
            "mood": "calm",
            "persona": "shallow_sleeper"
        }
        or None if no tracks available.
    """
    pool = get_all_tracks(include_archived=False)
    if not pool:
        return None

    history = _get_user_track_history(user_id)
    recent_tracks = _get_recent_track_ids(user_id, limit=2)

    scored = []
    for track in pool:
        score = _score_track(track, mood, persona, history, recent_tracks, user_id)
        scored.append((track, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    selected = _select_arc(scored, count=min(max_tracks, len(scored)))
    if not selected:
        return None

    playlist_tracks = []
    for i, (track, score, role) in enumerate(selected):
        playlist_tracks.append({
            "track_id": track.get("track_id", ""),
            "title": track.get("title", ""),
            "src": resolve_track_url(track),
            "gcs_url": track.get("gcs_url"),
            "role": role,
            "order": i,
            "score": round(score, 3),
            "energy_level": track.get("energy_level", "low"),
            "mood_tags": track.get("mood_tags", []),
        })

    month = datetime.now().strftime("%B")
    day = datetime.now().day
    name = f"{mood.title()} {month} {day}"

    playlist_id = _save_playlist(user_id, session_id, name, mood, persona, playlist_tracks)

    return {
        "playlist_id": playlist_id,
        "tracks": playlist_tracks,
        "mood": mood,
        "persona": persona,
        "name": name,
    }


def _score_track(track: dict, mood: str, persona: str | None,
                 history: dict, recent_tracks: set,
                 user_id: str = "") -> float:
    mood_scores = track.get("mood_scores", {})
    base = mood_scores.get(mood, 0.3)

    track_id = track.get("track_id", "")
    track_history = history.get(track_id, {})

    # History bonus: good ratings with this mood
    good_count = track_history.get("good_with_mood", {}).get(mood, 0)
    bad_count = track_history.get("bad_with_mood", {}).get(mood, 0)
    history_bonus = min(good_count * 0.1, 0.25) - min(bad_count * 0.08, 0.15)

    # Recency penalty
    recency_penalty = -0.12 if track_id in recent_tracks else 0

    # Persona modifier
    persona_bonus = 0
    if persona and persona in PERSONA_BOOSTS:
        boosts = PERSONA_BOOSTS[persona]
        for m, boost in boosts.items():
            persona_bonus += mood_scores.get(m, 0) * boost

    # Overall rating bonus
    avg = track.get("avg_rating")
    rating_bonus = ((avg - 3) * 0.05) if avg and avg > 0 else 0

    # Prefer user's own tracks
    owner_bonus = 0.15 if user_id and track.get("generated_by") == user_id else 0

    return max(0, base + history_bonus + recency_penalty + persona_bonus + rating_bonus + owner_bonus)


def _select_arc(scored: list[tuple], count: int = 5) -> list[tuple]:
    """Select tracks following a settling -> transition -> deep_sleep arc."""
    if not scored:
        return []

    if len(scored) == 1:
        track, score = scored[0]
        return [(track, score, "deep_sleep")]

    if len(scored) == 2:
        return [
            (scored[0][0], scored[0][1], "settling"),
            (scored[1][0], scored[1][1], "deep_sleep"),
        ]

    used = set()
    result = []

    # Slot 1: settling — prefer medium/high energy
    settling = _pick_by_energy(scored, {"high", "medium"}, used)
    if not settling:
        settling = _pick_best(scored, used)
    if settling:
        track, score = settling
        result.append((track, score, "settling"))
        used.add(track.get("track_id"))

    # Slot 2: transition — prefer medium/low energy
    transition = _pick_by_energy(scored, {"medium", "low"}, used)
    if not transition:
        transition = _pick_best(scored, used)
    if transition:
        track, score = transition
        result.append((track, score, "transition"))
        used.add(track.get("track_id"))

    # Remaining slots: deep_sleep — prefer low energy
    remaining = count - len(result)
    for _ in range(remaining):
        pick = _pick_by_energy(scored, {"low"}, used)
        if not pick:
            pick = _pick_best(scored, used)
        if pick:
            track, score = pick
            result.append((track, score, "deep_sleep"))
            used.add(track.get("track_id"))

    return result


def _pick_by_energy(scored: list[tuple], energy_levels: set, used: set):
    for track, score in scored:
        tid = track.get("track_id")
        if tid in used:
            continue
        if track.get("energy_level", "low") in energy_levels:
            return (track, score)
    return None


def _pick_best(scored: list[tuple], used: set):
    for track, score in scored:
        if track.get("track_id") not in used:
            return (track, score)
    return None


def _get_user_track_history(user_id: str) -> dict:
    """Aggregate track performance from sleep sessions.

    Returns: {track_id: {"good_with_mood": {"calm": 2}, "bad_with_mood": {"stressed": 1}}}
    """
    db = get_db()
    if db is None:
        return {}

    pipeline = [
        {"$match": {
            "user_id": user_id,
            "status": "reviewed",
            "review.skipped": {"$ne": True},
            "review.rating": {"$exists": True},
        }},
        {"$project": {
            "track_id": "$plan.soundscape_id",
            "mood": "$plan.mood",
            "rating": "$review.rating",
        }},
    ]

    results = {}
    try:
        for doc in db.sleep_sessions.aggregate(pipeline):
            tid = doc.get("track_id")
            if not tid:
                continue
            if tid not in results:
                results[tid] = {"good_with_mood": {}, "bad_with_mood": {}}
            mood = doc.get("mood", "calm")
            rating = doc.get("rating", 3)
            if rating >= 4:
                results[tid]["good_with_mood"][mood] = results[tid]["good_with_mood"].get(mood, 0) + 1
            elif rating <= 2:
                results[tid]["bad_with_mood"][mood] = results[tid]["bad_with_mood"].get(mood, 0) + 1
    except Exception:
        pass

    return results


def _get_recent_track_ids(user_id: str, limit: int = 2) -> set:
    db = get_db()
    if db is None:
        return set()
    try:
        cursor = db.sleep_sessions.find(
            {"user_id": user_id, "status": {"$in": ["reviewed", "completed"]}},
            {"plan.soundscape_id": 1},
            sort=[("created_at", -1)],
            limit=limit,
        )
        return {doc["plan"].get("soundscape_id") for doc in cursor if doc.get("plan", {}).get("soundscape_id")}
    except Exception:
        return set()


def _save_playlist(user_id: str, session_id: str | None, name: str,
                   mood: str, persona: str | None,
                   tracks: list[dict]) -> str | None:
    db = get_db()
    if db is None:
        return None

    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "session_id": ObjectId(session_id) if session_id else None,
        "name": name,
        "mood": mood,
        "persona": persona,
        "tracks": tracks,
        "completed": False,
        "tracks_played": 0,
        "post_rating": None,
        "created_at": now,
        "updated_at": now,
    }
    result = db.playlists.insert_one(doc)
    return str(result.inserted_id)


def get_playlist(playlist_id: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    try:
        doc = db.playlists.find_one({"_id": ObjectId(playlist_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
            if doc.get("session_id"):
                doc["session_id"] = str(doc["session_id"])
        return doc
    except Exception:
        return None


def update_playlist_progress(playlist_id: str, tracks_played: int):
    db = get_db()
    if db is None:
        return
    try:
        db.playlists.update_one(
            {"_id": ObjectId(playlist_id)},
            {"$set": {
                "tracks_played": tracks_played,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
    except Exception:
        pass


def complete_playlist(playlist_id: str, rating: int | None = None):
    db = get_db()
    if db is None:
        return
    try:
        update = {
            "completed": True,
            "updated_at": datetime.now(timezone.utc),
        }
        if rating is not None:
            update["post_rating"] = rating
        db.playlists.update_one(
            {"_id": ObjectId(playlist_id)},
            {"$set": update},
        )
    except Exception:
        pass
