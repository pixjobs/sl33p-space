#!/usr/bin/env python3
"""Backfill HLS manifests for existing tracks that have GCS audio but no HLS."""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

if not os.environ.get("GCS_BUCKET"):
    os.environ["GCS_BUCKET"] = "sl33p-space-music"

from db import get_db
from audio.music_gen import _convert_to_hls
from audio.gcs_storage import upload_hls, _get_client, _bucket_name


def backfill():
    db = get_db()
    if db is None:
        print("No database connection")
        return

    tracks = list(db.tracks.find({
        "gcs_url": {"$exists": True, "$ne": None},
        "hls_url": {"$exists": False},
    }))
    print(f"Found {len(tracks)} tracks to backfill")

    client = _get_client()
    bucket = client.bucket(_bucket_name())

    for i, track in enumerate(tracks):
        track_id = track["track_id"]
        gcs_obj = f"tracks/{track_id}.ogg"
        print(f"[{i+1}/{len(tracks)}] {track_id}: {track.get('title', '?')}")

        tmp_dir = tempfile.mkdtemp(prefix="hls_bf_")
        ogg_path = os.path.join(tmp_dir, f"{track_id}.ogg")

        try:
            blob = bucket.blob(gcs_obj)
            if not blob.exists():
                print(f"  SKIP — OGG not found in GCS")
                continue
            blob.download_to_filename(ogg_path)
            print(f"  Downloaded {os.path.getsize(ogg_path) // 1024}KB")

            hls_dir = _convert_to_hls(ogg_path, track_id)
            if not hls_dir:
                print(f"  SKIP — HLS conversion failed")
                continue

            hls_url = upload_hls(hls_dir, track_id)
            shutil.rmtree(hls_dir, ignore_errors=True)

            if not hls_url:
                print(f"  SKIP — HLS upload failed")
                continue

            db.tracks.update_one(
                {"track_id": track_id},
                {"$set": {"hls_url": hls_url}},
            )
            print(f"  OK — {hls_url}")

        except Exception as e:
            print(f"  ERROR — {e}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    print("Done")


if __name__ == "__main__":
    backfill()
