# sl33p-space

An AI-powered sleep companion that generates personalised music, builds mood-aware playlists, tracks sleep sessions, and learns from your history to improve recommendations over time. Built for the [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com/) (MongoDB track).

## Stack

- **AI/Agent** — Gemini 3 Flash (via Google ADK) for sleep recommendations and chat
- **Music generation** — Lyria 3 Pro for creating unique sleep tracks from text prompts
- **Database** — MongoDB Atlas for users, sessions, tracks, playlists, and insights
- **Agent tools** — MongoDB MCP server for session history, sleep trends, and factor correlations
- **Auth** — Firebase Authentication
- **Storage** — Google Cloud Storage for audio files (OGG + HLS)
- **Hosting** — Cloud Run (europe-west1), Cloud Build, Cloud Tasks
- **Frontend** — Flask + Jinja2, vanilla JS, Tailwind CSS

## What it does

You describe what you want to sleep to. The agent generates a track using Lyria, builds a mood-aware playlist, starts a timed session, and logs everything in MongoDB. The next night, it uses your sleep history — ratings, duration, mood, lifestyle factors — to recommend what worked best.

## Features

- **AI music generation** — Lyria creates unique sleep tracks from text prompts. Tracks are stored in GCS and catalogued in MongoDB with mood scores and energy levels.
- **Smart playlists** — Sessions play a curated sequence: settling → transition → deep sleep. The playlist engine scores tracks based on mood, persona, listening history, and past ratings.
- **HLS streaming** — Tracks are transcoded to HLS (AAC) with extended looping manifests for 8 hours of uninterrupted playback. iOS Safari plays HLS natively, surviving screen lock and background without JS.
- **Session tracking** — Duration, mood, lifestyle factors (caffeine, exercise, stress, etc.), and multi-metric reviews all persist to MongoDB.
- **Sleep insights** — Aggregated trends, factor correlations, and streak tracking derived from session history.
- **AI chat agent** — Gemini-powered conversational agent with MongoDB MCP tools for querying sleep data, finding best tracks, and spotting patterns.
- **Personas** — Shift worker, first responder, light sleeper, insomniac — each persona adjusts playlist scoring.
- **Tier system** — Free, Plus, and Tester tiers with generation credits, chat allowances, and referral bonuses.
- **Sleep journal** — Calendar view with per-day ratings, factors, and notes.
- **Cosmic backgrounds** — NASA APOD slideshow during sleep sessions.

## Architecture

```
User → Flask frontend → Gemini agent (ADK)
                              ↓
                        MongoDB MCP server
                              ↓
                        MongoDB Atlas
                        (sessions, tracks, users, playlists, insights)

Music generation:
  Cloud Tasks queue → Lyria 3 Pro → FFmpeg (OGG→HLS) → GCS bucket
```

## Run locally

```bash
pip install -r requirements.txt
export GOOGLE_API_KEY=your-key
export MONGODB_URI=mongodb+srv://...
export GCS_BUCKET=your-bucket          # optional, falls back to local storage
python run.py
# http://localhost:8090
```

## Deploy

```bash
# Use the deploy script (handles secrets, cert mount, env vars)
./scripts/deploy.sh
```

## Project structure

```
agent/          Gemini agent, prompts, MCP toolset loader
audio/          Music generation (Lyria), playlist engine, GCS storage, HLS conversion
config/         App and MCP server configuration
db/             MongoDB models (sessions, tracks, users, tiers, insights, packs)
scripts/        Deploy, backfill, and migration scripts
web/            Flask app, templates, static assets
```

## Hackathon context

- **Track:** MongoDB
- **Key integration:** MongoDB MCP server gives the Gemini agent direct access to sleep session data, enabling natural language queries like "what helped me sleep best last week?" or "which tracks work when I'm stressed?"
- **What makes it agentic:** The agent doesn't just answer questions — it reads your history, scores tracks, builds playlists, and adapts recommendations based on outcomes. The MCP tools let it reason over real user data rather than generic advice.

[MIT](LICENSE)
