"""
Lyria-powered sleep music generator.

Generates ambient sleep tracks from text prompts using Google's Lyria 3 models.
Tracks are cached -- same prompt never generates twice.

Uses NASA APOD data to create unique, data-driven ambient compositions.
"""

import hashlib
import json
import os
import requests
from typing import Optional


CACHE_DIR = "data/music"
CACHE_INDEX = os.path.join(CACHE_DIR, "index.json")

SLEEP_STYLE = (
    "Instrumental only, no vocals. "
    "Ambient, calming, suitable for sleep. "
    "Soft pads, gentle textures, slow evolution. "
    "Around 60 BPM. Loopable ending. "
    "No sudden changes, no percussion."
)

NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")


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


def generate_music(prompt: str, model: str = "lyria-3-clip-preview",
                   output_format: str = "mp3") -> dict:
    """Generate music from a text prompt. Returns cached version if available.

    Args:
        prompt: Music generation prompt (sleep style is appended automatically).
        model: lyria-3-clip-preview (30s) or lyria-3-pro-preview (full song).
        output_format: mp3 or wav (wav only for pro model).

    Returns:
        dict with path, prompt, cached, model keys.
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

        config_kwargs = {}
        if output_format == "wav" and model == "lyria-3-pro-preview":
            config_kwargs["config"] = types.GenerateContentConfig(
                response_modalities=["AUDIO", "TEXT"],
                response_mime_type="audio/wav",
            )

        response = client.models.generate_content(
            model=model,
            contents=full_prompt,
            **config_kwargs,
        )

        os.makedirs(CACHE_DIR, exist_ok=True)
        ext = output_format
        filepath = os.path.join(CACHE_DIR, f"{key}.{ext}")
        description = ""

        for part in response.parts:
            if part.text is not None:
                description = part.text
            elif part.inline_data is not None:
                with open(filepath, "wb") as f:
                    f.write(part.inline_data.data)

        if not os.path.exists(filepath):
            return {"error": "No audio data in response"}

        entry = {
            "path": filepath,
            "prompt": prompt,
            "model": model,
            "description": description,
            "format": ext,
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
        params = {"api_key": NASA_API_KEY}
        if date:
            params["date"] = date
        resp = requests.get("https://api.nasa.gov/planetary/apod", params=params, timeout=10)
        data = resp.json()

        title = data.get("title", "Deep Space")
        explanation = data.get("explanation", "")

        prompt = _apod_to_music_prompt(title, explanation)

        result = generate_music(prompt)
        result["nasa_title"] = title
        result["nasa_date"] = data.get("date", "")
        return result

    except Exception as e:
        return {"error": f"NASA API failed: {e}"}


def _apod_to_music_prompt(title: str, explanation: str) -> str:
    """Convert APOD data into a Lyria music prompt."""
    keywords = _extract_mood_keywords(explanation.lower())
    return (
        f"Ambient sleep music inspired by '{title}'. "
        f"Mood: {', '.join(keywords)}. "
        f"Create a dreamlike atmosphere that evokes the feeling of drifting through space. "
        f"Use warm synthesizer pads, subtle harmonic movement, and gentle celestial textures."
    )


def _extract_mood_keywords(text: str) -> list[str]:
    """Extract mood-relevant keywords from APOD text for music prompting."""
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


def list_generated_music() -> list[dict]:
    """List all cached generated music tracks."""
    index = _load_index()
    tracks = []
    for key, entry in index.items():
        if os.path.exists(entry.get("path", "")):
            tracks.append({
                "id": key,
                "prompt": entry.get("prompt", ""),
                "model": entry.get("model", ""),
                "description": entry.get("description", ""),
                "path": entry["path"],
                "size_kb": entry.get("size_kb", 0),
            })
    return tracks
