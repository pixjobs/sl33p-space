#!/usr/bin/env python3
"""
Migrate local music tracks to GCS and MongoDB.

Reads data/music/index.json, uploads each track to GCS (if enabled),
auto-tags moods, and inserts into the MongoDB tracks collection.
Idempotent — skips tracks that already exist in MongoDB.

Usage:
    python -m scripts.migrate_to_gcs
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio.gcs_storage import is_gcs_enabled, upload_track
from audio.mood_tagger import tag_track_moods
from db.tracks import get_track, upsert_track, ensure_indexes


INDEX_PATH = "data/music/index.json"


def _load_index() -> dict:
    if not os.path.exists(INDEX_PATH):
        print(f"No index file found at {INDEX_PATH}")
        return {}
    with open(INDEX_PATH) as f:
        return json.load(f)


def _measure_duration(path: str) -> float | None:
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(path)
        return round(len(audio) / 1000.0, 1)
    except Exception:
        return None


def migrate():
    index = _load_index()
    if not index:
        print("Nothing to migrate.")
        return

    ensure_indexes()
    gcs_on = is_gcs_enabled()
    print(f"GCS enabled: {gcs_on}")
    print(f"Found {len(index)} tracks in index.json")

    migrated = 0
    skipped = 0
    errors = 0

    for track_id, entry in index.items():
        if entry.get("archived"):
            continue

        existing = get_track(track_id)
        if existing:
            skipped += 1
            continue

        path = entry.get("path", "")
        if not os.path.exists(path):
            print(f"  SKIP {track_id}: file not found at {path}")
            skipped += 1
            continue

        try:
            prompt = entry.get("prompt", "")
            title = entry.get("title", prompt[:60])
            mood_data = tag_track_moods(prompt)
            duration = _measure_duration(path)
            size_kb = round(os.path.getsize(path) / 1024, 1)

            gcs_url = None
            gcs_bucket = None
            gcs_object = None
            if gcs_on:
                gcs_url = upload_track(path, track_id)
                if gcs_url:
                    gcs_bucket = os.environ.get("GCS_BUCKET", "")
                    gcs_object = f"tracks/{track_id}.ogg"
                    print(f"  UPLOADED {track_id} -> {gcs_url}")

            track_doc = {
                "track_id": track_id,
                "title": title,
                "prompt": prompt,
                "description": entry.get("description", ""),
                "model": entry.get("model", "lyria"),
                "format": "ogg",
                "size_kb": size_kb,
                "duration_seconds": duration,
                "local_path": path,
                "gcs_bucket": gcs_bucket,
                "gcs_object": gcs_object,
                "gcs_url": gcs_url,
                "storage_mode": "gcs" if gcs_url else "local",
                "mood_tags": mood_data.get("mood_tags", []),
                "mood_scores": mood_data.get("mood_scores", {}),
                "energy_level": mood_data.get("energy_level", "low"),
                "generated_by": entry.get("user_id"),
                "is_preset": entry.get("is_preset", False),
                "visibility": "public",
                "archived": False,
                "play_count": 0,
                "avg_rating": None,
                "total_ratings": 0,
                "pack_id": None,
            }

            upsert_track(track_doc)
            migrated += 1
            print(f"  OK {track_id}: {title} [{', '.join(mood_data.get('mood_tags', []))}]")

        except Exception as e:
            errors += 1
            print(f"  ERROR {track_id}: {e}")

    print(f"\nDone: {migrated} migrated, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    migrate()
