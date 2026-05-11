"""
Lyria-powered sleep music generator.

Generates ambient sleep tracks from text prompts using Google's Lyria 3 Clip model.
Tracks are cached -- same prompt never generates twice.

Uses NASA APOD data to create unique, data-driven ambient compositions.
"""

import hashlib
import json
import os
import requests
import shutil
from typing import Optional


CACHE_DIR = "data/music"
CACHE_INDEX = os.path.join(CACHE_DIR, "index.json")

def _text_model() -> str:
    try:
        with open("config/config.json") as f:
            return json.load(f).get("agent", {}).get("model", "gemini-flash-latest")
    except Exception:
        return "gemini-flash-latest"

SLEEP_STYLE = (
    "Instrumental only, no vocals. "
    "Ambient, calming, suitable for sleep. "
    "Soft pads, gentle textures, slow evolution. "
    "Around 60 BPM. Loopable ending. "
    "No sudden changes, no percussion."
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
}


def _cache_key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def _load_index() -> dict:
    if os.path.exists(CACHE_INDEX):
        with open(CACHE_INDEX) as f:
            return json.load(f)
    return {}


def _save_index(index: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_INDEX, "w") as f:
        json.dump(index, f, indent=2)


TARGET_DURATION_MINUTES = 5
CROSSFADE_MS = 3000


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

    extended_path = filepath.replace(".mp3", "_ext.mp3")
    result.export(extended_path, format="mp3")

    shutil.move(extended_path, filepath)
    return filepath


def generate_music(prompt: str, title: str = "",
                   model: str = "lyria-3-clip-preview") -> dict:
    """Generate music from a text prompt. Returns cached version if available.

    Args:
        prompt: Music generation prompt (sleep style is appended automatically).
        title: Human-readable title for the track.
        model: lyria-3-clip-preview (30s clips).

    Returns:
        dict with path, prompt, title, cached, model keys.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_API_KEY not set. Cannot generate music."}

    full_prompt = f"{prompt}\n\n{SLEEP_STYLE}"
    key = _cache_key(full_prompt)
    index = _load_index()

    if key in index and os.path.exists(index[key]["path"]):
        return {**index[key], "cached": True}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
            ),
        )

        os.makedirs(CACHE_DIR, exist_ok=True)
        filepath = os.path.join(CACHE_DIR, f"{key}.mp3")
        description = ""

        for part in response.candidates[0].content.parts:
            if part.text is not None:
                description = part.text
            elif part.inline_data is not None:
                with open(filepath, "wb") as f:
                    f.write(part.inline_data.data)

        if not os.path.exists(filepath):
            return {"error": "No audio data in response"}

        _loop_with_crossfade(filepath)

        entry = {
            "path": filepath,
            "prompt": prompt,
            "title": title or prompt[:60],
            "model": model,
            "description": description,
            "format": "mp3",
            "size_kb": os.path.getsize(filepath) // 1024,
        }
        index[key] = entry
        _save_index(index)

        return {**entry, "cached": False}

    except ImportError:
        return {"error": "google-genai package not installed"}
    except Exception as e:
        return {"error": str(e)}


def generate_from_nasa_apod(date: Optional[str] = None) -> dict:
    """Generate a unique sleep track inspired by today's NASA Astronomy Picture of the Day."""
    try:
        nasa_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        params = {"api_key": nasa_key}
        if date:
            params["date"] = date
        resp = requests.get("https://api.nasa.gov/planetary/apod", params=params, timeout=10)
        data = resp.json()

        title = data.get("title", "Deep Space")
        explanation = data.get("explanation", "")

        prompt = _apod_to_music_prompt(title, explanation)

        result = generate_music(prompt, title=f"NASA: {title}")
        result["nasa_title"] = title
        result["nasa_date"] = data.get("date", "")
        return result

    except Exception as e:
        return {"error": f"NASA API failed: {e}"}


def _apod_to_music_prompt(title: str, explanation: str) -> str:
    keywords = _extract_mood_keywords(explanation.lower())
    return (
        f"Ambient sleep music inspired by '{title}'. "
        f"Mood: {', '.join(keywords)}. "
        f"Create a dreamlike atmosphere that evokes the feeling of drifting through space. "
        f"Use warm synthesizer pads, subtle harmonic movement, and gentle celestial textures."
    )


def _extract_mood_keywords(text: str) -> list[str]:
    mood_map = {
        "bright": "luminous, uplifting",
        "dark": "deep, mysterious",
        "nebula": "ethereal, misty",
        "galaxy": "vast, expansive",
        "star": "sparkling, warm",
        "moon": "gentle, reflective",
        "sun": "radiant, warm",
        "planet": "orbiting, steady",
        "comet": "flowing, transient",
        "supernova": "powerful, fading",
        "aurora": "shimmering, colorful",
        "dust": "soft, diffuse",
        "cluster": "layered, rich",
        "void": "minimal, spacious",
        "eclipse": "dramatic, transitional",
        "ring": "circular, hypnotic",
    }
    found = []
    for keyword, mood in mood_map.items():
        if keyword in text:
            found.append(mood)
    return found[:4] or ["serene, cosmic"]


def _track_entry(key: str, entry: dict) -> dict:
    return {
        "id": key,
        "title": entry.get("title", entry.get("prompt", "")[:60]),
        "prompt": entry.get("prompt", ""),
        "model": entry.get("model", ""),
        "description": entry.get("description", ""),
        "filename": os.path.basename(entry["path"]),
        "path": entry["path"],
        "size_kb": entry.get("size_kb", 0),
    }


def list_generated_music() -> list[dict]:
    """List all cached generated music tracks (excludes archived)."""
    index = _load_index()
    tracks = []
    for key, entry in index.items():
        if entry.get("archived"):
            continue
        if os.path.exists(entry.get("path", "")):
            tracks.append(_track_entry(key, entry))
    return tracks


def list_archived_music() -> list[dict]:
    """List all archived music tracks."""
    index = _load_index()
    tracks = []
    for key, entry in index.items():
        if not entry.get("archived"):
            continue
        if os.path.exists(entry.get("path", "")):
            tracks.append(_track_entry(key, entry))
    return tracks


def delete_track(track_id: str) -> dict:
    """Delete a track permanently — removes the file and index entry."""
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


def archive_track(track_id: str) -> dict:
    """Archive a track — moves it to data/music/archive/ and flags it."""
    index = _load_index()
    if track_id not in index:
        return {"error": f"Track {track_id} not found"}
    entry = index[track_id]
    src = entry.get("path", "")
    if not os.path.exists(src):
        return {"error": "Track file not found on disk"}
    archive_dir = os.path.join(CACHE_DIR, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    dest = os.path.join(archive_dir, os.path.basename(src))
    shutil.move(src, dest)
    entry["path"] = dest
    entry["archived"] = True
    index[track_id] = entry
    _save_index(index)
    return {"archived": track_id}


def unarchive_track(track_id: str) -> dict:
    """Unarchive a track — moves it back to the main music directory."""
    index = _load_index()
    if track_id not in index:
        return {"error": f"Track {track_id} not found"}
    entry = index[track_id]
    src = entry.get("path", "")
    if not os.path.exists(src):
        return {"error": "Track file not found on disk"}
    dest = os.path.join(CACHE_DIR, os.path.basename(src))
    shutil.move(src, dest)
    entry["path"] = dest
    entry.pop("archived", None)
    index[track_id] = entry
    _save_index(index)
    return {"unarchived": track_id}


def get_preset_prompts() -> dict[str, str]:
    """Return the curated preset prompts for the UI."""
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
    """Return random built-in suggestions when Gemini isn't available."""
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
    """Simple variation when Gemini isn't available."""
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
