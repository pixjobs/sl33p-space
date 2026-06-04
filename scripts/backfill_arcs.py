#!/usr/bin/env python3
"""Backfill continuous-arc audio for sessions that have a playlist but no arc.

Older sessions store a multi-track playlist whose advancement depends on the
browser's `ended` event (which freezes when the phone locks). This stitches each
such session's playlist into one continuous, infinitely-looping source so
overnight playback survives screen lock. Safe to re-run — already-stitched
sessions are skipped.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

if not os.environ.get("GCS_BUCKET"):
    os.environ["GCS_BUCKET"] = "sl33p-space-music"

from db import get_db
from db.sessions import update_session_arc
from audio.playlist import get_playlist
from audio.music_gen import stitch_playlist_arc


def backfill(limit: int = 50):
    db = get_db()
    if db is None:
        print("No database connection")
        return

    sessions = list(db.sleep_sessions.find({
        "playlist_id": {"$ne": None},
        "arc_audio": None,
        "status": {"$in": ["active", "completed", "reviewed"]},
    }).sort("created_at", -1).limit(limit))
    print(f"Found {len(sessions)} sessions to backfill")

    for i, session in enumerate(sessions):
        sid = str(session["_id"])
        print(f"[{i+1}/{len(sessions)}] session {sid}")

        playlist = get_playlist(session["playlist_id"])
        if not playlist or not playlist.get("tracks"):
            print("  SKIP — no playlist tracks")
            continue

        arc = stitch_playlist_arc(playlist["tracks"], sid)
        if "error" in arc:
            print(f"  SKIP — {arc['error']}")
            continue

        update_session_arc(sid, arc)
        print(f"  OK — {arc.get('hls_url') or arc.get('stitched_ogg_url')}")

    print("Done")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    backfill(n)
