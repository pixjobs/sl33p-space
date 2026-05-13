# sl33p-space

Your AI sleep coach. Tell it once how you want to sleep — it handles the rest every night.

Built with [Google ADK](https://github.com/google/adk-python) + Gemini + Lyria for the [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com/) (MongoDB track).

## What it does

- **AI-generated sleep music** — Describe what you want ("warm piano with rain textures"), Lyria generates a unique track. Cached and shared across users.
- **Bedtime automation** — Configure your routine once via natural language. The agent plays your preferred music, fades out, and logs the session. No conversation needed at bedtime.
- **Learns from history** — Tracks what you played, when, and how long. The agent recommends what works best for you based on completion rates and patterns.
- **Shared music library** — Every generated track is stored in MongoDB and available to all users. Community tracks with high completion rates surface first.

## Architecture

```
Browser
  │
  ├── Chat UI ──► Google ADK Agent (Gemini)
  │                  │
  │                  ├── MongoDB MCP Server ──► MongoDB Atlas
  │                  │     • music_library (shared tracks)
  │                  │     • users (profiles + credits)
  │                  │     • sleep_sessions (playback history)
  │                  │     • routines (nightly schedules)
  │                  │
  │                  ├── Lyria (google.genai)
  │                  │     • AI music generation
  │                  │
  │                  └── Playback Tools
  │                        • Schedule, play, fade, stop
  │
  ├── Browser Audio Player (HTML5 <audio>)
  │
  └── Scheduler (autonomous nightly routines)
```

## Quick start

```bash
# Clone and install
git clone https://github.com/yourname/sl33p-space.git
cd sl33p-space
pip install -r requirements.txt

# Set environment variables
export GOOGLE_API_KEY=your-gemini-api-key
export MONGODB_URI=mongodb+srv://...

# Run
python run.py
# Open http://localhost:8090
```


## Product flow

1. **Open the plan page** — Firebase/dev-mode identifies the user and the app loads MongoDB-backed sleep stats, pending reviews, recent sessions, track library, persona, tier, and generated music.
2. **Review last night** — A pending review updates `sleep_sessions.review`, giving MongoDB fresh signal for ratings, factors, and duration.
3. **Pick tonight's mood** — The plan page preselects the MongoDB-recommended mood when history exists, then sorts tracks by matching mood tags.
4. **Start sleep** — The app creates a MongoDB `sleep_sessions` document and, when possible, a mood/persona-aware playlist before sending the user to the immersive sleep view.
5. **Agent learns** — Gemini/ADK uses `get_mongodb_sleep_insights` plus MongoDB MCP tools to explain recommendations with actual track, mood, and factor patterns.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Gemini API key for agent + Lyria music generation |
| `MONGODB_URI` | Yes | MongoDB Atlas connection string |
| `MONGODB_DATABASE` | No | Database name (default: `sl33p-space`) |

## Cloud Run deployment

```bash
gcloud run deploy sl33p-space \
  --source . \
  --set-env-vars GOOGLE_API_KEY=$GOOGLE_API_KEY,MONGODB_URI=$MONGODB_URI \
  --allow-unauthenticated
```

## Hackathon track

**MongoDB** — See [HACKATHON.md](HACKATHON.md) for submission details, judging criteria mapping, and architecture notes.

## License

MIT
