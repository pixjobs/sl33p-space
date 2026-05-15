# sl33p-space

An AI sleep agent that generates music, plans sessions, and learns from your history — built for the [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com/).

## Stack

Gemini + Google ADK + Lyria (music gen) + MongoDB Atlas

## What it does

You describe what you want to sleep to. The agent generates a track, plans a mood-aware playlist, starts a session, and logs everything in MongoDB. Next time, it uses your history to recommend what worked.

## Features

- **Generate music** — Lyria creates unique sleep tracks from a text prompt. Tracks are stored in MongoDB and shared across users.
- **Smart playlists** — Sessions play a sequence: settling → transition → deep sleep. The agent picks tracks based on your mood, persona, and past ratings.
- **Session tracking** — Duration, mood, lifestyle factors, and ratings all go to MongoDB. The agent uses this data for recommendations.
- **MongoDB MCP** — Custom agent tools for session history, best tracks, sleep trends, and factor correlations.

## Run locally

```bash
pip install -r requirements.txt
export GOOGLE_API_KEY=your-key
export MONGODB_URI=mongodb+srv://...
python run.py
# http://localhost:8090
```

## Deploy

```bash
gcloud run deploy sl33p-space \
  --source . \
  --set-env-vars GOOGLE_API_KEY=$GOOGLE_API_KEY,MONGODB_URI=$MONGODB_URI \
  --allow-unauthenticated
```

## Tracks

MongoDB — agent built with Gemini + MongoDB MCP server for sleep session management and history-based recommendations.

[MIT](LICENSE)
