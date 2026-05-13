"""
Keyword-based mood tagger for sleep music tracks.

Analyzes prompt text to assign mood scores and energy level.
Deterministic and fast — no API calls required.
"""

MOOD_KEYWORDS: dict[str, list[str]] = {
    "wired": [
        "bright", "sparkling", "crystal", "sharp", "electric", "energetic",
        "vivid", "glittering", "shimmering", "arpeggiated", "pulsing",
        "glowing", "radiant", "luminous", "flickering",
    ],
    "stressed": [
        "warm", "soft", "gentle", "cozy", "comfort", "soothing", "safe",
        "embrace", "blanket", "nurture", "cradle", "shelter", "calm",
        "reassuring", "peaceful", "serene",
    ],
    "restless": [
        "rhythmic", "ocean", "rain", "flow", "movement", "wind", "wave",
        "current", "tide", "ripple", "drift", "floating", "rocking",
        "train", "journey", "wandering",
    ],
    "tired": [
        "deep", "slow", "minimal", "dark", "heavy", "sub-bass", "drone",
        "vast", "infinite", "void", "space", "abyss", "descent",
        "sinking", "fading", "dissolving", "theta",
    ],
    "calm": [
        "zen", "still", "silence", "temple", "meditation", "peaceful",
        "garden", "bowl", "chime", "bell", "prayer", "sacred", "ancient",
        "tranquil", "serene", "quiet", "breathe",
    ],
}

ENERGY_FROM_MOOD = {
    "wired": "high",
    "stressed": "medium",
    "restless": "medium",
    "tired": "low",
    "calm": "low",
}

THRESHOLD = 0.3


def tag_track_moods(prompt: str) -> dict:
    """Analyze a music prompt and return mood tags, scores, and energy level.

    Returns:
        {
            "mood_tags": ["calm", "tired"],
            "mood_scores": {"wired": 0.1, "stressed": 0.3, ...},
            "energy_level": "low"
        }
    """
    words = set(prompt.lower().split())

    scores = {}
    for mood, keywords in MOOD_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in words or any(kw in w for w in words))
        scores[mood] = round(min(hits / max(len(keywords) * 0.3, 1), 1.0), 2)

    tags = [mood for mood, score in scores.items() if score >= THRESHOLD]

    if not tags:
        tags = ["calm"]
        scores["calm"] = max(scores.get("calm", 0), 0.4)

    dominant = max(scores, key=scores.get)
    energy = ENERGY_FROM_MOOD.get(dominant, "low")

    return {
        "mood_tags": tags,
        "mood_scores": scores,
        "energy_level": energy,
    }
