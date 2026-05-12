#!/usr/bin/env python3
"""sl33p-space entry point.

Usage:
  Local dev:   python run.py
  Production:  gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 run:app
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv(".env.local", override=True)
load_dotenv(".env")


def load_config():
    config_path = os.path.join("config", "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {
        "audio": {"max_volume": 80, "default_volume": 40, "sounds_dir": "data/sounds"},
        "web": {"host": "0.0.0.0", "port": 8080},
    }


def _make_session_logger():
    from datetime import datetime
    log_path = os.path.join("data", "sleep_log.json")

    def log_session(info: dict):
        os.makedirs("data", exist_ok=True)
        entries = []
        if os.path.exists(log_path):
            with open(log_path) as f:
                entries = json.load(f)
        entries.append({
            "profile": "default",
            "sound_type": info.get("sound", ""),
            "duration_minutes": round(info.get("duration_seconds", 0) / 60, 1),
            "completed": info.get("completed", False),
            "notes": "",
            "timestamp": datetime.now().isoformat(),
        })
        with open(log_path, "w") as f:
            json.dump(entries, f, indent=2)

    return log_session


def create_app():
    config = load_config()
    audio_cfg = config.get("audio", {})

    from audio.player import AudioPlayer
    from audio.library import SoundLibrary
    from audio.scheduler import Scheduler

    player = AudioPlayer(
        max_volume=audio_cfg.get("max_volume", 80),
        default_volume=audio_cfg.get("default_volume", 40),
        on_stop_callback=_make_session_logger(),
    )
    library = SoundLibrary(sounds_dir=audio_cfg.get("sounds_dir", "data/sounds"))
    scheduler = Scheduler(player, library)

    from agent.agent import init as agent_init, make_chat_handler
    agent_init(player, library, scheduler)
    chat_handler = make_chat_handler(config)

    scheduler.start()

    from web.app import create_app as create_flask_app
    flask_app = create_flask_app(player, library, scheduler, agent_runner=chat_handler)

    @flask_app.template_filter("basename")
    def basename_filter(path):
        return os.path.splitext(os.path.basename(path))[0] if path else ""

    sound_icons = {
        "brown_noise": "~",
        "pink_noise": "~",
        "white_noise": "~",
        "rain": "/",
        "ocean_waves": "=",
        "binaural_beats": "))",
        "ambient_atmosphere": "*",
        "lullaby_drone": "#",
    }

    @flask_app.template_filter("sound_icon")
    def sound_icon_filter(sound_type):
        return sound_icons.get(sound_type, "~")

    return flask_app, config


app, _config = create_app()


def main():
    web_cfg = _config.get("web", {})
    host = web_cfg.get("host", "0.0.0.0")
    port = int(os.environ.get("PORT", web_cfg.get("port", 8090)))

    mcp_servers = [s["name"] for s in _config.get("mcp", {}).get("servers", []) if s.get("enabled")]
    has_adk = os.environ.get("GOOGLE_API_KEY")
    dev_mode = os.environ.get("DEV_MODE", "").lower() in ("true", "1", "yes")
    print(f"sl33p-space")
    print(f"  Web UI:  http://localhost:{port}")
    print(f"  Auth:    {'DEV_MODE (no login required)' if dev_mode else 'Firebase Auth'}")
    print(f"  Agent:   {'Gemini (ADK)' if has_adk else 'Fallback (set GOOGLE_API_KEY for Gemini)'}")
    print(f"  Audio:   browser (HTML5)")
    print(f"  MCP:     {', '.join(mcp_servers) if mcp_servers else 'none configured'}")
    print()

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
