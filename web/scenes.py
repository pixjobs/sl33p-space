import logging
import os
from datetime import date

import requests

from db.assets import cache_apod, get_cached_apod, get_latest_apod, get_apod_pool

log = logging.getLogger(__name__)


def get_apod() -> dict | None:
    today = date.today().isoformat()
    cached = get_cached_apod(today)
    if cached and cached.get("media_type") == "image":
        return {"url": cached.get("hdurl") or cached.get("url"), "title": cached.get("title", ""), "explanation": cached.get("explanation", "")}

    api_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
    try:
        resp = requests.get(
            "https://api.nasa.gov/planetary/apod",
            params={"api_key": api_key, "date": today},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        cache_apod(
            date_str=today,
            url=data.get("url", ""),
            hdurl=data.get("hdurl", ""),
            title=data.get("title", ""),
            explanation=data.get("explanation", ""),
            media_type=data.get("media_type", "image"),
        )

        if data.get("media_type") != "image":
            fallback = get_latest_apod()
            if fallback:
                return {"url": fallback.get("hdurl") or fallback.get("url"), "title": fallback.get("title", ""), "explanation": fallback.get("explanation", "")}
            return None

        return {"url": data.get("hdurl") or data.get("url"), "title": data.get("title", ""), "explanation": data.get("explanation", "")}

    except Exception as e:
        log.warning("APOD fetch failed: %s", e)
        fallback = get_latest_apod()
        if fallback:
            return {"url": fallback.get("hdurl") or fallback.get("url"), "title": fallback.get("title", ""), "explanation": fallback.get("explanation", "")}
        return None


def get_apod_collection(count: int = 20) -> list[dict]:
    pool = get_apod_pool(limit=30)
    if len(pool) >= count:
        return pool[:count]

    api_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
    try:
        resp = requests.get(
            "https://api.nasa.gov/planetary/apod",
            params={"api_key": api_key, "count": min(count, 30)},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json()

        for item in items:
            if item.get("media_type") != "image":
                continue
            apod_date = item.get("date", "")
            cache_apod(
                date_str=apod_date,
                url=item.get("url", ""),
                hdurl=item.get("hdurl", ""),
                title=item.get("title", ""),
                explanation=item.get("explanation", ""),
                media_type="image",
            )

        pool = get_apod_pool(limit=count)
        return pool
    except Exception as e:
        log.warning("APOD collection fetch failed: %s", e)
        return pool


def generate_scene_image(theme: str, prompt: str) -> str | None:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        scene_dir = os.path.join("data", "scenes", theme)
        os.makedirs(scene_dir, exist_ok=True)

        import hashlib
        key = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        filename = f"{theme}_{key}.png"
        filepath = os.path.join(scene_dir, filename)

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                with open(filepath, "wb") as f:
                    f.write(part.inline_data.data)
                from db.assets import cache_scene_image
                cache_scene_image(theme, filepath, prompt=prompt, title=f"{theme.title()} scene")
                return filepath

    except Exception as e:
        log.warning("Scene generation failed: %s", e)

    return None
