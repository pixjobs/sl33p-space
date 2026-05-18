"""
Google Cloud Storage integration for sl33p-space music tracks.

Enabled when GCS_BUCKET env var is set. Falls back to local storage otherwise.
Uses Application Default Credentials on GCP, or GOOGLE_APPLICATION_CREDENTIALS locally.
"""

import os

_client = None


def is_gcs_enabled() -> bool:
    return bool(os.environ.get("GCS_BUCKET"))


def _bucket_name() -> str:
    return os.environ.get("GCS_BUCKET", "sl33p-space-music")


def _get_client():
    global _client
    if _client is not None:
        return _client
    from google.cloud import storage
    _client = storage.Client()
    return _client


def upload_track(local_path: str, track_id: str) -> str | None:
    """Upload an OGG file to GCS. Returns the public URL or None on failure."""
    if not is_gcs_enabled():
        return None
    if not os.path.exists(local_path):
        return None

    try:
        client = _get_client()
        bucket = client.bucket(_bucket_name())
        object_name = f"tracks/{track_id}.ogg"
        blob = bucket.blob(object_name)
        blob.upload_from_filename(local_path, content_type="audio/ogg")
        return f"https://storage.googleapis.com/{_bucket_name()}/{object_name}"
    except Exception as e:
        import sys
        print(f"GCS upload failed for {track_id}: {e}", file=sys.stderr)
        return None


def get_track_url(track_doc: dict) -> str:
    """Resolve playback URL from a track document."""
    if track_doc.get("gcs_url"):
        return track_doc["gcs_url"]
    local = track_doc.get("local_path", "")
    if local:
        return "/media/music/" + os.path.basename(local)
    return ""


def get_gcs_info(track_id: str) -> dict:
    """Return GCS bucket/object/url for a track_id."""
    bucket = _bucket_name()
    obj = f"tracks/{track_id}.ogg"
    url = f"https://storage.googleapis.com/{bucket}/{obj}"
    return {
        "gcs_bucket": bucket,
        "gcs_object": obj,
        "gcs_url": url,
    }


def upload_hls(local_dir: str, track_id: str) -> str | None:
    """Upload HLS manifest + segments to GCS. Returns the looping manifest URL."""
    if not is_gcs_enabled():
        return None
    import glob
    m3u8_loop = os.path.join(local_dir, f"{track_id}_loop.m3u8")
    if not os.path.exists(m3u8_loop):
        return None

    try:
        client = _get_client()
        bucket = client.bucket(_bucket_name())

        files = glob.glob(os.path.join(local_dir, f"{track_id}*"))
        content_types = {
            ".m3u8": "application/vnd.apple.mpegurl",
            ".ts": "video/mp2t",
        }
        for fpath in files:
            ext = os.path.splitext(fpath)[1]
            ct = content_types.get(ext)
            if not ct:
                continue
            obj_name = f"tracks/hls/{os.path.basename(fpath)}"
            blob = bucket.blob(obj_name)
            blob.upload_from_filename(fpath, content_type=ct)

        return f"https://storage.googleapis.com/{_bucket_name()}/tracks/hls/{track_id}_loop.m3u8"
    except Exception as e:
        import sys
        print(f"HLS upload failed for {track_id}: {e}", file=sys.stderr)
        return None


def delete_from_gcs(gcs_object: str) -> bool:
    """Delete an object from GCS. Returns True on success."""
    if not is_gcs_enabled():
        return False
    try:
        client = _get_client()
        bucket = client.bucket(_bucket_name())
        blob = bucket.blob(gcs_object)
        blob.delete()
        return True
    except Exception:
        return False


def get_signed_url(gcs_object: str, expiry_minutes: int = 60) -> str | None:
    """Generate a signed URL for private content."""
    if not is_gcs_enabled():
        return None
    try:
        from datetime import timedelta
        client = _get_client()
        bucket = client.bucket(_bucket_name())
        blob = bucket.blob(gcs_object)
        return blob.generate_signed_url(expiration=timedelta(minutes=expiry_minutes))
    except Exception:
        return None
