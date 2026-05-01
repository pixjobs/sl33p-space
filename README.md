# sl33p-space

Sleep optimization assistant for families. Runs on Raspberry Pi as a bedroom audio server with a web interface for parents.

Built with [Google ADK](https://github.com/google/adk-python) + Gemini for the [Google Cloud Rapid Agent Hackathon](https://devpost.com/).

## What it does

- **Plays sleep sounds** on a Pi speaker: brown noise, pink noise, rain, ocean waves, binaural beats, lullaby drones
- **Gemini-powered agent** understands natural language: "Play rain sounds for Lily, fade out in 30 minutes"
- **Bedtime schedules** that trigger automatically each night with fade-out
- **Family profiles** with per-child volume limits and sound preferences
- **Web UI** accessible from any phone on the local network

## Quick start

```bash
pip install -r requirements.txt
python run.py
# Open http://localhost:8080
```

For Gemini agent support:
```bash
export GOOGLE_API_KEY=your-key-here
python run.py
```

## Architecture

```
sl33p-space/
├── agent/          # Google ADK agent (Gemini + tools)
├── audio/          # Sound generator, player, scheduler, library
├── web/            # Flask web interface
├── config/         # Configuration
└── run.py          # Entry point
```

The **agent** interprets natural language and calls tools. The **audio engine** generates and plays sounds. The **web interface** provides a dashboard, chat panel, profile management, and schedule management. Everything connects through `run.py`.

## Raspberry Pi setup

```bash
# On your Pi:
git clone https://github.com/yourname/sl33p-space.git
cd sl33p-space
pip install -r requirements.txt
python run.py
# Access from phone: http://<pi-ip>:8080
```

Requires: Python 3.10+, one of `aplay`/`mpg123`/`ffplay` for audio playback.

## MCP partner integration

The agent architecture supports MCP partners via ADK's `McpToolset`. Partner integration will be added when hackathon partners are announced.

## License

MIT
