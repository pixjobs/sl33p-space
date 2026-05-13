#!/usr/bin/env python3
"""
Generate NASA APOD-inspired sleep tracks using Lyria Pro.

Reads NASA APOD (Astronomy Picture of the Day) data and generates
lyrics-free, instrumental tracks inspired by celestial phenomena.

Run: python3 scripts/generate_nasa_tracks.py

Requires:
  - NASA_API_KEY in environment (https://api.nasa.gov/)
  - GOOGLE_API_KEY in environment (for Lyria generation)
  - Run the Flask server first: python run.py
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error

NASA_API_KEY = os.environ.get("NASA_API_KEY", "")
BASE_URL = "http://localhost:8090"


def fetch_apod(nasa_key: str, date: str = "") -> dict:
    """Fetch a single NASA APOD entry."""
    url = f"https://api.nasa.gov/planetary/apod?api_key={nasa_key}"
    if date:
        url += f"&date={date}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_apod_bulk(nasa_key: str, count: int = 20) -> list:
    """Fetch recent APOD entries for bulk track generation."""
    from datetime import date, timedelta

    entries = []
    today = date.today()
    for i in range(count):
        d = (today - timedelta(days=i)).isoformat()
        try:
            entry = fetch_apod(nasa_key, d)
            entries.append(entry)
        except Exception as e:
            print(f"  [WARN] Skipping {d}: {e}")
        time.sleep(3)  # Rate limit NASA API
    return entries


def build_track_prompts(apod_entries: list) -> list:
    """Convert NASA APOD entries into Lyria track generation prompts."""

    style_guidance = (
        "Instrumental only, no vocals. "
        "Mellow, lofi, slow, Interstellar-inspired. "
        "Theta-wave / sleep / therapy / meditation style. "
        "Warm analog pads, slow evolution, tape-delay textures. "
        "Around 40 BPM. Gentle sine sub-bass at theta frequency. "
        "Loopable ending. No sudden changes, no percussion, no EDM."
    )

    prompts = []

    for entry in apod_entries:
        title = entry.get("title", "Unknown Cosmos")
        explanation = entry.get("explanation", "")[:200]  # First 200 chars
        copyright_info = entry.get("copyright", "")
        media_type = entry.get("media_type", "")

        # Extract key concepts from the explanation
        celestial_objects = []
        if any(w in explanation.lower() for w in ["nebula", "cloud", "dust"]):
            celestial_objects.append("cosmic dust clouds and nebulae")
        if any(w in explanation.lower() for w in ["star", "stars", "formation"]):
            celestial_objects.append("star formation regions")
        if any(w in explanation.lower() for w in ["galaxy"]):
            celestial_objects.append("galactic structure")
        if any(w in explanation.lower() for w in ["planet", "planet"]):
            celestial_objects.append("planetary atmosphere")
        if any(w in explanation.lower() for w in ["supernova", "explos"]):
            celestial_objects.append("supernova remnants")
        if any(w in explanation.lower() for w in ["black hole", "singularity"]):
            celestial_objects.append("event horizon shadows and gravitational lensing")
        if any(w in explanation.lower() for w in ["comet", "asteroid"]):
            celestial_objects.append("icy celestial bodies")
        if any(w in explanation.lower() for w in ["moon", "satellite"]):
            celestial_objects.append("solar system moon surfaces")
        if any(w in explanation.lower() for w in ["eclipse"]):
            celestial_objects.append("celestial alignment and eclipse")
        if any(w in explanation.lower() for w in ["aurora", "polar"]):
            celestial_objects.append("aurora and magnetic fields")
        if any(w in explanation.lower() for w in ["cosmic microwave", "background", "cobe", "wmap", "planck"]):
            celestial_objects.append("cosmic microwave background radiation")

        if not celestial_objects:
            celestial_objects.append("vast interstellar space")

        object_str = " and ".join(celestial_objects[:3])

        # Build NASA-inspired prompt
        prompt = (
            f"Sleep ambient inspired by '{title}' - {object_str}. "
            f"{'Warm analog pad drones with tape-delay stretching notes across light years. ' if 'cloud' in object_str or 'dust' in object_str else ''}"
            f"Slow, meditative atmosphere with gentle sub-bass. "
            f"{copyright_info if copyright_info else 'Public domain.'} "
            f"{style_guidance}"
        )

        # Clean title for filename
        safe_title = "".join(c if c.isalnum() or c == " " else "" for c in title)[:50].strip()

        prompts.append({
            "prompt": prompt,
            "title": safe_title,
            "nasa_source": title,
            "date": entry.get("date", ""),
            "url": entry.get("url", ""),
        })

    return prompts


def generate_track(prompt: str, title: str) -> dict:
    """Send a generation request to the running server."""
    try:
        data = json.dumps({"prompt": prompt, "title": title}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/api/music/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def main():
    nasa_key = NASA_API_KEY
    if not nasa_key:
        print("ERROR: Set NASA_API_KEY in environment to use this script.")
        print("Get one free at: https://api.nasa.gov/")
        print("Example: export NASA_API_KEY='YOUR_KEY_HERE'")
        print("Example: export GOOGLE_API_KEY='YOUR_KEY_HERE'")
        sys.exit(1)

    google_key = os.environ.get("GOOGLE_API_KEY", "")
    if not google_key:
        print("ERROR: Set GOOGLE_API_KEY in environment for Lyria generation.")
        print("Example: export GOOGLE_API_KEY='YOUR_KEY_HERE'")
        sys.exit(1)

    print("=" * 60)
    print("  NASA APOD → Sleep Track Generator")
    print("=" * 60)

    # Fetch APOD data
    print("\n[1/3] Fetching NASA APOD data...")
    entries = fetch_apod_bulk(nasa_key, count=5)  # Start with 5 to test
    print(f"  Retrieved {len(entries)} APOD entries")

    # Build prompts
    print("\n[2/3] Building track prompts...")
    prompts = build_track_prompts(entries)

    for i, p in enumerate(prompts):
        print(f"  {i+1}. {p['title']}")
        print(f"     Source: NASA - {p['nasa_source']}")
        print(f"     Prompt: {p['prompt'][:100]}...")
        print()

    # Confirm generation
    answer = input("Generate these tracks? (yes/no): ").strip().lower()
    if answer != "yes":
        print("Cancelled.")
        sys.exit(0)

    # Generate tracks
    print("\n[3/3] Generating tracks...")
    results = []

    for i, p in enumerate(prompts):
        print(f"  Generating {i+1}/{len(prompts)}: {p['title']}...", end="", flush=True)
        result = generate_track(p["prompt"], p["title"])

        if result.get("error"):
            print(f" FAILED: {result['error']}")
        else:
            print(f" OK - {result.get('duration', '?')}s")
            results.append({
                "title": p["title"],
                "nasa_source": p["nasa_source"],
                "status": "generated",
            })

        # Rate limit Lyria
        time.sleep(5)

    print("\n" + "=" * 60)
    print("  Generation Complete")
    print("=" * 60)

    for r in results:
        print(f"  ✓ {r['title']} (NASA: {r['nasa_source']})")

    print("\nRefresh /plan to see new tracks in the Sound Lab.")
    print("Restart the server if tracks don't appear: pkill -f 'python run.py' && python run.py")


if __name__ == "__main__":
    main()
