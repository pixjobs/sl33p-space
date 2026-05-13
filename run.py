#!/usr/bin/env python3
"""sl33p-space entry point.

Usage:
  Local dev:   python run.py
  Production:  gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 run:app
"""

import json
import os

from dotenv import load_dotenv

load_dotenv(".env.local", override=True)
load_dotenv(".env")


def load_config():
    config_path = os.path.join("config", "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {"web": {"host": "0.0.0.0", "port": 8090}}


def create_app():
    config = load_config()

    from agent.agent import make_chat_handler
    chat_handler = make_chat_handler(config)

    from web.app import create_app as create_flask_app
    flask_app = create_flask_app(agent_runner=chat_handler)

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
