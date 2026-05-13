"""
Unit test for Lyria music generation.
Uses a temp folder so no pollution of actual music library.

Run: python3 -m pytest tests/test_lyria_gen.py -v
     or: python3 tests/test_lyria_gen.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env so GOOGLE_API_KEY is available
from dotenv import load_dotenv
load_dotenv(".env.local", override=True)

def run_test():
    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        print("SKIP: GOOGLE_API_KEY not set")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # Swap cache dir and config temporarily
        import audio.music_gen as gen

        original_cache = gen.CACHE_DIR
        original_load_config = gen._load_config

        # Patch cache dir
        gen.CACHE_DIR = tmpdir
        gen.CACHE_INDEX = os.path.join(tmpdir, "index.json")

        # Patch _load_config to return music config with our model
        def patched_load_config():
            return {"music": {"model": "lyria-3-pro-preview", "target_duration_minutes": 10}}

        gen._load_config = patched_load_config

        try:
            print("=" * 60)
            print("Lyria Generation Test Suite")
            print("=" * 60)

            # ── Test 1: Short prompt ──
            print("\n[Test 1] Short prompt (12 words)")
            r = gen.generate_music(
                prompt="ambient space music no vocals mellow",
                title="test_short",
                user_id="test",
            )
            _print_result("short", r)

            # ── Test 2: Medium prompt ──
            print("\n[Test 2] Medium prompt (30 words)")
            r = gen.generate_music(
                prompt="deep space meditation inspired by 47 Tucanae globular cluster with warm analog pads",
                title="test_medium",
                user_id="test",
            )
            _print_result("medium", r)

            # ── Test 3: Long prompt with SLEEP_STYLE appended ──
            print("\n[Test 3] Long prompt + SLEEP_STYLE (full)")
            r = gen.generate_music(
                prompt="deep space ambient with cosmic dust clouds and warm analog synth drones",
                title="test_full",
                user_id="test",
            )
            _print_result("full", r)

            # ── Test 4: Try SLEEP_STYLE_INTERSTELLAR ──
            print("\n[Test 4] Interstellar style")
            r = gen.generate_music(
                prompt="nocturnal space station ambient capsule in orbit",
                title="test_interstellar",
                user_id="test",
            )
            _print_result("interstellar", r)

            # ── Test 5: Direct genai call (bypass music_gen) ──
            print("\n[Test 5] Direct genai call (bypass)")
            _direct_test(key)

            # ── Test 6: Try different model ──
            print("\n[Test 6] Try lyria-3 instead of lyria-3-pro-preview")
            gen.CACHE_DIR = tmpdir
            gen._load_config = lambda: {"music": {"model": "lyria-3", "target_duration_minutes": 10}}
            r = gen.generate_music(
                prompt="ambient space music no vocals mellow",
                title="test_lyria3",
                user_id="test",
            )
            _print_result("lyria3", r)

        finally:
            gen.CACHE_DIR = original_cache
            gen._load_config = original_load_config

    print("\nDone. Temp dir cleaned up.")


def _print_result(name, r):
    if "error" in r:
        print(f"  FAIL: {r['error']}")
    else:
        print(f"  OK: {r['title']} ({r.get('size_kb', '?')}KB)")


def _direct_test(api_key):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompts = [
        "ambient space music no vocals",
        "ambient space music no vocals mellow",
        "ambient space music instrumental calm sleep",
        "lofi ambient sleep music warm pads",
    ]

    for i, prompt in enumerate(prompts):
        try:
            r = client.models.generate_content(
                model="lyria-3-pro-preview",
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["audio"]),
            )
            has_content = r.candidates and r.candidates[0].content
            if has_content:
                audio_parts = [
                    p for p in r.candidates[0].content.parts
                    if p.inline_data and p.inline_data.data
                ]
                audio_bytes = sum(len(p.inline_data.data) for p in audio_parts)
                print(f"  Prompt '{prompt}': OK, {audio_bytes//1024}KB audio")
            else:
                fr = r.candidates[0].finish_reason if r.candidates else "N/A"
                print(f"  Prompt '{prompt}': FAIL (finish={fr})")
        except Exception as e:
            print(f"  Prompt '{prompt}': ERROR: {e}")


if __name__ == "__main__":
    run_test()
