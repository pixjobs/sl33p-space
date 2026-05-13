"""
Lyria-powered sleep music generator.

Generates ambient sleep tracks from text prompts using Google's Lyria 3 Clip model.
Tracks are stored in MongoDB (tracks collection) and optionally uploaded to GCS.
"""

import hashlib
import json
import os
import shutil

from audio.mood_tagger import tag_track_moods
from audio.gcs_storage import is_gcs_enabled, upload_track as gcs_upload, get_gcs_info, delete_from_gcs
from db.tracks import (
    upsert_track, get_track, get_all_tracks, ensure_indexes,
    archive_track as db_archive, unarchive_track as db_unarchive,
    delete_track as db_delete,
)


LOCAL_CACHE_DIR = "data/music"
LOCAL_CACHE_INDEX = os.path.join(LOCAL_CACHE_DIR, "index.json")


def _load_config() -> dict:
    try:
        with open("config/config.json") as f:
            return json.load(f)
    except Exception:
        return {}


def _text_model() -> str:
    return _load_config().get("agent", {}).get("model", "gemini-flash-latest")


def _music_config() -> dict:
    return _load_config().get("music", {})


SLEEP_STYLE = (
    "Ambient sleep music, instrumental only, no vocals. "
    "Mellow, lofi, slow, warm analog pads. "
    "Around 40 BPM, no percussion, no EDM."
)

SLEEP_STYLE_INTERSTELLAR = (
    "Interstellar-style ambient music, instrumental only, no vocals. "
    "Slow evolving pads, tape-delay textures, deep sub-bass. "
    "Around 40 BPM, mellow, lofi, no percussion, no EDM."
)

PRESET_PROMPTS = {
    "Analog Warmth": "Warm analog synthesizer drones with gentle tape saturation, deep sub-bass, slowly evolving harmonic layers",
    "Rainy Window": "Soft rainfall on a window with distant thunder and muffled wind, cozy indoor atmosphere",
    "Celestial Dream": "Celestial ambient music with crystalline arpeggios, vast reverb spaces, and gentle cosmic textures",
    "Deep Ocean": "Deep ocean underwater ambience with whale songs, gentle currents, and bioluminescent shimmer",
    "Zen Garden": "Japanese garden at night, gentle wind chimes, bamboo water feature, distant temple bell",
    "Aurora": "Northern lights inspired ambient, shimmering high-frequency textures, aurora borealis in sound",
    "Forest Night": "Nighttime forest ambience with soft crickets, distant owl calls, gentle breeze through pine trees",
    "Moonlit Piano": "Sparse piano notes with long reverb tails, gentle pad accompaniment, moonlit atmosphere",
    "Starfield": "Vast interstellar space, deep resonant bass, tiny sparkling grain textures floating in infinite darkness",
    "Warm Vinyl": "Old vinyl record hiss and warmth, slow jazz chords barely audible through warm analog crackle",
    "Night Train": "Gentle rhythmic train movement on tracks, distant whistle, soft interior cabin ambience, rain on windows",
    "Cathedral Echo": "Massive cathedral reverb space, single sustained organ note evolving into warm harmonic overtones",
    "Tidal Pool": "Shallow tide pool at sunset, gentle lapping water, distant seabirds, warm golden-hour atmosphere",
    "Himalayan Bowl": "Tibetan singing bowls resonating in a mountain cave, deep overtones, meditative stillness",
    "Tucanae Deep": "Slow deep space meditation inspired by globular star cluster 47 Tucanae. Warm analog pads like cosmic gas clouds, tape-delay stretching notes across light years. Minimal piano. Theta sub-bass. No percussion, no vocals, no EDM.",
    "Carina Drift": "Ambient space music inspired by the Great Carina Nebula. Ethereal synth drones in low frequencies, slow chord changes every 30 seconds. Soft granular textures shimmering like starlight through cosmic dust. No beat, no vocals.",
    "Event Horizon Lullaby": "Interstellar-inspired slow motion ambient. Deep space organ tones mixed with warm analog strings, moving imperceptibly slow. A single repeated melody echoing through vast reverb. Theta-wave sub-bass. No percussion, no vocals.",
    "Ringfall Theta": "Slow descending pad progression creating a sensation of falling gently through Saturn's atmosphere. Warm analog warmth throughout. Soft bell tones marking each chord change. Extremely slow tempo, deeply mellow.",
    "Long Night Protocol": "Slow-motion deep space lofi. Vinyl-crackle texture layered over warm pad drones. Gentle bell-like piano tones spaced 40 seconds apart, decaying into infinity. Sub-bass at 3 Hz. No beat, no vocals.",
    "Station Sleep Cycle": "Nocturnal space station ambient. Cold but warm-tinted synthesizer pads representing a sleeping capsule in orbit. Gentle arpeggiated patterns at 40 BPM with heavy reverb. Distant static textures. Slowly evolving lullaby.",
}


def _cache_key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


# Legacy index.json helpers — kept for migration and fallback
def _load_index() -> dict:
    if os.path.exists(LOCAL_CACHE_INDEX):
        with open(LOCAL_CACHE_INDEX) as f:
            return json.load(f)
    return {}


def _save_index(index: dict):
    os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
    with open(LOCAL_CACHE_INDEX, "w") as f:
        json.dump(index, f, indent=2)


TARGET_DURATION_MINUTES = 10
CROSSFADE_MS = 3000
MAX_TRACKS_PER_USER = 10
MAX_TRACKS_TOTAL = 50


def _loop_with_crossfade(filepath: str, target_minutes: int = TARGET_DURATION_MINUTES,
                         crossfade_ms: int = CROSSFADE_MS) -> str:
    try:
        from pydub import AudioSegment
    except ImportError:
        return filepath

    clip = AudioSegment.from_file(filepath)
    clip_ms = len(clip)
    if clip_ms < 1000:
        return filepath

    target_ms = target_minutes * 60 * 1000
    if clip_ms >= target_ms:
        return filepath

    result = clip
    while len(result) < target_ms:
        result = result.append(clip, crossfade=min(crossfade_ms, clip_ms // 2))

    result = result[:target_ms]

    fade_ms = 5000
    result = result.fade_in(fade_ms).fade_out(fade_ms)

    base, ext = os.path.splitext(filepath)
    extended_path = f"{base}_ext{ext}"
    if ext == ".ogg":
        result.export(extended_path, format="ogg", codec="libopus",
                      parameters=["-b:a", "128k"])
    else:
        result.export(extended_path, format=ext.lstrip("."))

    shutil.move(extended_path, filepath)
    return filepath


def generate_music(prompt: str, title: str = "",
                   model: str = "", user_id: str = "default") -> dict:
    """Generate music from a text prompt. Returns cached version if available."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_API_KEY not set. Cannot generate music."}

    cfg = _music_config()
    if not model:
        model = cfg.get("model", "lyria-3-pro-preview")
    max_per_user = cfg.get("max_tracks_per_user", MAX_TRACKS_PER_USER)
    max_total = cfg.get("max_tracks_total", MAX_TRACKS_TOTAL)

    full_prompt = f"{prompt}\n\n{SLEEP_STYLE}"
    key = _cache_key(full_prompt)

    # Check MongoDB cache first
    existing = get_track(key)
    if existing:
        src = existing.get("gcs_url") or (
            "/media/music/" + os.path.basename(existing["local_path"])
            if existing.get("local_path") else ""
        )
        return {
            "path": existing.get("local_path", ""),
            "prompt": existing.get("prompt", prompt),
            "title": existing.get("title", ""),
            "model": existing.get("model", model),
            "description": existing.get("description", ""),
            "format": existing.get("format", "ogg/opus"),
            "size_kb": existing.get("size_kb", 0),
            "src": src,
            "gcs_url": existing.get("gcs_url"),
            "mood_tags": existing.get("mood_tags", []),
            "cached": True,
        }

    # Fallback: check legacy index.json
    index = _load_index()
    if key in index and os.path.exists(index[key].get("path", "")):
        entry = index[key]
        _migrate_index_entry(key, entry, prompt, model)
        return {**entry, "cached": True}

    # Check limits
    all_tracks = get_all_tracks()
    active_count = len(all_tracks)
    if active_count >= max_total:
        return {"error": f"Library is full ({max_total} tracks). Archive or delete tracks to make room."}

    user_count = sum(1 for t in all_tracks if t.get("generated_by") == user_id)
    if user_count >= max_per_user:
        return {"error": f"You've reached your limit of {max_per_user} tracks. Archive or delete one to generate a new track."}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
        filepath = os.path.join(LOCAL_CACHE_DIR, f"{key}.ogg")
        description = ""

        response = client.models.generate_content(
            model=model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["audio"],
            ),
        )

        audio_received = False
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.text is not None:
                    description = part.text
                elif part.inline_data is not None and part.inline_data.data:
                    with open(filepath, "wb") as f:
                        f.write(part.inline_data.data)
                    audio_received = True

        if not audio_received or not os.path.exists(filepath):
            return {"error": "No audio data received from model"}

        target_mins = cfg.get("target_duration_minutes", TARGET_DURATION_MINUTES)
        _loop_with_crossfade(filepath, target_minutes=target_mins)

        # Mood tagging
        mood_data = tag_track_moods(prompt)

        # GCS upload
        gcs_url = None
        gcs_info = {}
        if is_gcs_enabled():
            gcs_url = gcs_upload(filepath, key)
            if gcs_url:
                gcs_info = get_gcs_info(key)

        # Duration
        duration_seconds = None
        try:
            from pydub import AudioSegment
            clip = AudioSegment.from_file(filepath)
            duration_seconds = round(len(clip) / 1000)
        except Exception:
            pass

        track_title = title or prompt[:60]

        # Persist to MongoDB
        track_data = {
            "track_id": key,
            "title": track_title,
            "prompt": prompt,
            "full_prompt": full_prompt,
            "description": description,
            "model": model,
            "format": "ogg/opus",
            "size_kb": os.path.getsize(filepath) // 1024,
            "duration_seconds": duration_seconds,
            "local_path": filepath,
            "storage_mode": "gcs" if gcs_url else "local",
            "generated_by": user_id,
            "is_preset": prompt in PRESET_PROMPTS.values(),
            **mood_data,
            **gcs_info,
        }
        if gcs_url:
            track_data["gcs_url"] = gcs_url

        upsert_track(track_data)

        # Also write to legacy index.json for backward compat
        index[key] = {
            "path": filepath,
            "prompt": prompt,
            "title": track_title,
            "model": model,
            "description": description,
            "format": "ogg/opus",
            "size_kb": os.path.getsize(filepath) // 1024,
            "generated_by": user_id,
        }
        _save_index(index)

        src = gcs_url or f"/media/music/{key}.ogg"

        return {
            "path": filepath,
            "prompt": prompt,
            "title": track_title,
            "model": model,
            "description": description,
            "format": "ogg/opus",
            "size_kb": os.path.getsize(filepath) // 1024,
            "src": src,
            "gcs_url": gcs_url,
            "mood_tags": mood_data.get("mood_tags", []),
            "cached": False,
        }

    except ImportError:
        return {"error": "google-genai package not installed"}
    except Exception as e:
        return {"error": str(e)}


def _migrate_index_entry(key: str, entry: dict, prompt: str, model: str):
    """Migrate a legacy index.json entry to MongoDB tracks collection."""
    mood_data = tag_track_moods(prompt)
    local_path = entry.get("path", "")

    gcs_url = None
    gcs_info = {}
    if is_gcs_enabled() and os.path.exists(local_path):
        gcs_url = gcs_upload(local_path, key)
        if gcs_url:
            gcs_info = get_gcs_info(key)

    track_data = {
        "track_id": key,
        "title": entry.get("title", prompt[:60]),
        "prompt": entry.get("prompt", prompt),
        "full_prompt": f"{prompt}\n\n{SLEEP_STYLE}",
        "description": entry.get("description", ""),
        "model": entry.get("model", model),
        "format": entry.get("format", "ogg/opus"),
        "size_kb": entry.get("size_kb", 0),
        "local_path": local_path,
        "storage_mode": "gcs" if gcs_url else "local",
        "generated_by": entry.get("generated_by", "system"),
        "is_preset": entry.get("prompt", prompt) in PRESET_PROMPTS.values(),
        **mood_data,
        **gcs_info,
    }
    if gcs_url:
        track_data["gcs_url"] = gcs_url

    upsert_track(track_data)


def _track_entry(track: dict) -> dict:
    """Format a MongoDB track document for API responses."""
    src = track.get("gcs_url") or (
        "/media/music/" + os.path.basename(track["local_path"])
        if track.get("local_path") else ""
    )
    return {
        "id": track.get("track_id", ""),
        "title": track.get("title", ""),
        "prompt": track.get("prompt", ""),
        "model": track.get("model", ""),
        "description": track.get("description", ""),
        "filename": os.path.basename(track.get("local_path", "")),
        "path": track.get("local_path", ""),
        "size_kb": track.get("size_kb", 0),
        "src": src,
        "gcs_url": track.get("gcs_url"),
        "mood_tags": track.get("mood_tags", []),
        "energy_level": track.get("energy_level", "low"),
        "avg_rating": track.get("avg_rating"),
    }


def list_generated_music() -> list[dict]:
    """List all active generated music tracks."""
    tracks = get_all_tracks(include_archived=False)
    if tracks:
        return [_track_entry(t) for t in tracks]

    # Fallback to legacy index.json
    index = _load_index()
    result = []
    for key, entry in index.items():
        if entry.get("archived"):
            continue
        if os.path.exists(entry.get("path", "")):
            result.append({
                "id": key,
                "title": entry.get("title", entry.get("prompt", "")[:60]),
                "prompt": entry.get("prompt", ""),
                "model": entry.get("model", ""),
                "description": entry.get("description", ""),
                "filename": os.path.basename(entry["path"]),
                "path": entry["path"],
                "size_kb": entry.get("size_kb", 0),
                "src": "/media/music/" + os.path.basename(entry["path"]),
                "mood_tags": [],
                "energy_level": "low",
            })
    return result


def list_archived_music() -> list[dict]:
    """List all archived music tracks."""
    from db.tracks import get_all_tracks as _get_all
    tracks = _get_all(include_archived=True)
    return [_track_entry(t) for t in tracks if t.get("archived")]


def delete_track(track_id: str) -> dict:
    """Delete a track permanently."""
    track = get_track(track_id)
    if not track:
        # Try legacy
        index = _load_index()
        if track_id not in index:
            return {"error": f"Track {track_id} not found"}
        entry = index[track_id]
        path = entry.get("path", "")
        if os.path.exists(path):
            os.remove(path)
        del index[track_id]
        _save_index(index)
        return {"deleted": track_id}

    # Delete from GCS
    if track.get("gcs_object"):
        delete_from_gcs(track["gcs_object"])

    # Delete local file
    local = track.get("local_path", "")
    if local and os.path.exists(local):
        os.remove(local)

    # Delete from MongoDB
    db_delete(track_id)

    # Also clean legacy index
    index = _load_index()
    if track_id in index:
        del index[track_id]
        _save_index(index)

    return {"deleted": track_id}


def archive_track(track_id: str) -> dict:
    """Archive a track."""
    track = get_track(track_id)
    if not track:
        # Try legacy
        index = _load_index()
        if track_id not in index:
            return {"error": f"Track {track_id} not found"}
        entry = index[track_id]
        src = entry.get("path", "")
        if not os.path.exists(src):
            return {"error": "Track file not found on disk"}
        archive_dir = os.path.join(LOCAL_CACHE_DIR, "archive")
        os.makedirs(archive_dir, exist_ok=True)
        dest = os.path.join(archive_dir, os.path.basename(src))
        shutil.move(src, dest)
        entry["path"] = dest
        entry["archived"] = True
        index[track_id] = entry
        _save_index(index)
        return {"archived": track_id}

    db_archive(track_id)

    # Also update legacy index
    index = _load_index()
    if track_id in index:
        index[track_id]["archived"] = True
        _save_index(index)

    return {"archived": track_id}


def unarchive_track(track_id: str) -> dict:
    """Unarchive a track."""
    track = get_track(track_id)
    if not track:
        index = _load_index()
        if track_id not in index:
            return {"error": f"Track {track_id} not found"}
        entry = index[track_id]
        src = entry.get("path", "")
        if not os.path.exists(src):
            return {"error": "Track file not found on disk"}
        dest = os.path.join(LOCAL_CACHE_DIR, os.path.basename(src))
        shutil.move(src, dest)
        entry["path"] = dest
        entry.pop("archived", None)
        index[track_id] = entry
        _save_index(index)
        return {"unarchived": track_id}

    db_unarchive(track_id)

    index = _load_index()
    if track_id in index:
        index[track_id].pop("archived", None)
        _save_index(index)

    return {"unarchived": track_id}


def get_preset_prompts() -> dict[str, str]:
    return dict(PRESET_PROMPTS)


_EXTRA_PROMPTS = [
    {"title": "Velvet Drift", "prompt": "Ultra-slow evolving velvet pad textures with deep warmth, like sinking into soft fabric"},
    {"title": "Bioluminescence", "prompt": "Underwater bioluminescent glow, tiny sparkling synth grains floating in dark ambient space"},
    {"title": "Frozen Lake", "prompt": "Ice cracking on a frozen lake at midnight, crystalline resonances, deep cold stillness"},
    {"title": "Nebula Nursery", "prompt": "Star-forming nebula ambience, cosmic gas clouds translated to warm granular synthesis"},
    {"title": "Temple Rain", "prompt": "Gentle rain inside an ancient stone temple, long reverb, occasional low singing bowl"},
    {"title": "Moth Wings", "prompt": "Delicate fluttering textures like moth wings near a lamp, soft granular synthesis, barely-there"},
    {"title": "Desert Stars", "prompt": "Empty desert at night under a million stars, vast silence with occasional warm wind tones"},
    {"title": "Coral Reef", "prompt": "Shallow coral reef at sunset, gentle water movement, muffled clicks and soft harmonic shimmer"},
    {"title": "Old Radio", "prompt": "Warm analog radio static slowly resolving into gentle melody fragments, tape hiss, nostalgia"},
    {"title": "Snow Globe", "prompt": "Miniature snow globe world, tiny music box melody slowed 10x, glittery particle textures"},
    {"title": "Silk Thread", "prompt": "Single silk thread vibrating in slow motion, pure sine waves with gentle harmonic overtones"},
    {"title": "Lantern Float", "prompt": "Paper lanterns floating on still water at night, warm glowing tones, gentle ripple textures"},
]

_SUGGEST_SYSTEM = """You are a creative music director for a sleep/ambient music generator.
Generate exactly 4 unique sleep music prompt ideas. Each should be vivid, specific, and evocative.
Focus on textures, atmospheres, and imagery — not genres or artist references.
Keep prompts under 30 words. Give each a short 2-3 word title.

Respond with a JSON array only, no markdown:
[{"title": "...", "prompt": "..."}, ...]"""

_VARIATION_SYSTEM = """You are a creative music director. Given an original sleep music prompt,
create a variation that keeps the essence but shifts the mood, texture, or perspective.
For example: make it deeper, warmer, more minimal, shift the setting, change the time of day.
Keep the variation under 30 words. Give it a short 2-3 word title.

Respond with JSON only, no markdown:
{"title": "...", "prompt": "..."}"""


def suggest_prompts(existing_titles: list[str] | None = None) -> list[dict]:
    """Use Gemini to suggest 4 creative sleep music prompts."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return _fallback_suggestions(existing_titles)

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        user_msg = "Suggest 4 fresh sleep music ideas."
        if existing_titles:
            user_msg += f" Avoid these existing titles: {', '.join(existing_titles[:10])}"

        response = client.models.generate_content(
            model=_text_model(),
            contents=user_msg,
            config={"system_instruction": _SUGGEST_SYSTEM, "temperature": 1.2},
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        suggestions = json.loads(text)
        if isinstance(suggestions, list) and len(suggestions) > 0:
            return suggestions[:4]
    except Exception:
        pass

    return _fallback_suggestions(existing_titles)


def _fallback_suggestions(existing_titles: list[str] | None = None) -> list[dict]:
    import random
    pool = list(_EXTRA_PROMPTS)
    if existing_titles:
        pool = [p for p in pool if p["title"] not in existing_titles]
    random.shuffle(pool)
    return pool[:4]


def suggest_variation(original_prompt: str) -> dict:
    """Use Gemini to create a variation of an existing track's prompt."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return _fallback_variation(original_prompt)

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=_text_model(),
            contents=f"Original prompt: {original_prompt}",
            config={"system_instruction": _VARIATION_SYSTEM, "temperature": 1.0},
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
        if isinstance(result, dict) and "prompt" in result:
            return result
    except Exception:
        pass

    return _fallback_variation(original_prompt)


def _fallback_variation(original_prompt: str) -> dict:
    import random
    modifiers = [
        "but deeper and more minimal",
        "reimagined as an underwater scene",
        "with added warmth and tape saturation",
        "shifted to a colder, more crystalline atmosphere",
        "as if heard from very far away, with vast reverb",
        "slowed down and more spacious",
    ]
    mod = random.choice(modifiers)
    return {"title": "Variation", "prompt": f"{original_prompt}, {mod}"}


def seed_n_tracks(n: int = 5) -> dict:
    """Generate up to n tracks from random presets not already in the library."""
    import random
    generated = 0
    errors = []
    candidates = []

    for title, prompt in PRESET_PROMPTS.items():
        full_prompt = f"{prompt}\n\n{SLEEP_STYLE}"
        key = _cache_key(full_prompt)
        if not get_track(key):
            # Also check legacy
            index = _load_index()
            if key not in index or not os.path.exists(index[key].get("path", "")):
                candidates.append((title, prompt))

    random.shuffle(candidates)
    candidates = candidates[:n]

    for title, prompt in candidates:
        result = generate_music(prompt, title=title, user_id="system")
        if "error" in result:
            errors.append(f"{title}: {result['error']}")
        else:
            generated += 1
    return {"generated": generated, "errors": errors}


def seed_library() -> dict:
    """Generate tracks from all preset prompts that don't already exist."""
    generated = 0
    skipped = 0
    errors = []

    for title, prompt in PRESET_PROMPTS.items():
        full_prompt = f"{prompt}\n\n{SLEEP_STYLE}"
        key = _cache_key(full_prompt)
        if get_track(key):
            skipped += 1
            continue
        index = _load_index()
        if key in index and os.path.exists(index[key].get("path", "")):
            skipped += 1
            continue

        result = generate_music(prompt, title=title, user_id="system")
        if "error" in result:
            errors.append(f"{title}: {result['error']}")
        else:
            generated += 1

    return {"generated": generated, "skipped": skipped, "errors": errors}


def migrate_index_to_mongodb() -> dict:
    """One-time migration: read index.json and populate MongoDB tracks collection."""
    index = _load_index()
    migrated = 0
    skipped = 0

    for key, entry in index.items():
        if get_track(key):
            skipped += 1
            continue

        prompt = entry.get("prompt", "")
        _migrate_index_entry(key, entry, prompt, entry.get("model", ""))
        migrated += 1

    if migrated > 0:
        ensure_indexes()

    return {"migrated": migrated, "skipped": skipped, "total": len(index)}
