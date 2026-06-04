# sl33p-space

An agentic sleep companion for people whose sleep is hard-won — shift workers, emergency-services staff, light sleepers, and insomniacs. Every night the agent plans a continuous audio arc (settling → transition → deep sleep), verifies the choice against the user's own history via MongoDB MCP, and shows its reasoning before you approve. After each session you review the outcome, and the agent remembers what worked to adapt future nights. Built for the **Building Agents for Real-World Challenges** hackathon (MongoDB track).

## The problem

Poor sleep is a real, costly health problem, worst for people on irregular or high-stress schedules. Generic sleep apps hand you a static library and leave the work to you: which sound, how long, why it failed last night. sl33p-space turns that into an agent's job — it reasons over *your* logged outcomes, decides and acts on a multi-step plan each night, keeps the audio unbroken until morning, and learns from the result. The music is the medium; the agent is the product.

## Stack

- **AI/Agent** — Google ADK + Gemini 3 Flash for autonomous nightly planning and adaptive recommendations
- **Music generation** — Lyria 3 Pro for creating unique sleep tracks from text prompts
- **Database** — MongoDB Atlas for users, sessions, tracks, playlists, insights, and agent memory
- **Agent tools** — MongoDB MCP server for load-bearing session queries, trend analysis, and track verification
- **Auth** — Firebase Authentication
- **Storage** — Google Cloud Storage for audio files (OGG + HLS)
- **Hosting** — Cloud Run (europe-west1), Cloud Build, Cloud Tasks
- **Frontend** — Flask + Jinja2, vanilla JS, Tailwind CSS

## What makes it agentic

**Nightly Mission** — Each evening when you open `/plan`, the agent autonomously builds a plan before you say anything: it analyses your sleep history via MongoDB MCP, selects a track, composes a continuous overnight arc, predicts the outcome, and surfaces the reasoning in a visual stepper (analyse history → verify via MCP → choose track → compose arc → predict outcome → ready). You stay in control — approve and start, swap the track, or regenerate the whole plan.

**Load-bearing + visible MongoDB MCP** — The agent's track recommendation runs a real MongoDB aggregation query (via the MongoDB MCP server through ADK) to verify average ratings for the chosen track under current conditions. The query and result are surfaced in the UI with an "MCP" badge, proving the integration is load-bearing and not cosmetic.

**Continuous overnight audio stream** — The agent stitches the night's arc into one infinitely-looping source that loops at the OS media layer, so audio no longer cuts off mid-night when the phone screen locks. Session recovery anchors the elapsed clock to the server and resumes seamlessly on return.

**Agent memory + close-the-loop** — After each session you rate the outcome. The agent records what worked in MongoDB (`agent_memory` collection) and cites those learnings on the next night's recommendation.

**Personable coach + multi-night experiments** — A consistent coach (Nova) greets you, reviews last night, and remembers you across nights. When your data suggests a lever — e.g. screens or caffeine appear to cost you a star — the coach proposes a short, opt-in experiment, runs it across several nights as you review each one, then measures the result against your history and reports back. Plan → run-over-days → measure → adapt: agentic behaviour grounded entirely in MongoDB, no music generation required.

## Features

- **AI music generation** — Lyria creates unique sleep tracks from text prompts. Tracks are stored in GCS and catalogued in MongoDB with mood scores and energy levels.
- **Smart playlists** — Sessions play a curated sequence: settling → transition → deep sleep. The playlist engine scores tracks based on mood, persona, listening history, and past ratings.
- **Continuous HLS streaming** — Tracks are transcoded to HLS (AAC) with extended looping manifests stitched into one infinite source for 8+ hours of uninterrupted playback. iOS Safari plays HLS natively, surviving screen lock and background without JS.
- **Session tracking** — Duration, mood, lifestyle factors (caffeine, exercise, stress, etc.), and multi-metric reviews all persist to MongoDB.
- **Sleep insights** — Aggregated trends, factor correlations, and streak tracking derived from session history.
- **AI chat agent** — Gemini-powered conversational agent with MongoDB MCP tools for querying sleep data, finding best tracks, and spotting patterns.
- **Personas** — Shift worker, first responder, light sleeper, insomniac — each persona adjusts playlist scoring.
- **Tier system** — Free, Plus, and Tester tiers with generation credits, chat allowances, and referral bonuses.
- **Sleep journal** — Calendar view with per-day ratings, factors, and notes.
- **Cosmic backgrounds** — NASA APOD slideshow during sleep sessions.

## How it goes beyond chat

The agent doesn't wait for you to ask. When you open `/plan`, it:

1. **Analyses history** — Aggregates MongoDB session data: recent nights, mood × track matrix, factor correlations
2. **Verifies via MCP** — Runs a MongoDB aggregation query through the MCP server to check average ratings for the chosen track
3. **Chooses track** — Selects the best track from your library based on mood, persona, and past outcomes
4. **Composes continuous arc** — Builds a seamless settling → transition → deep-sleep playlist stitched into one looping source
5. **Predicts outcome** — Estimates rating and confidence from historical data
6. **Shows the Mission** — Surfaces all steps in a visual stepper with numbered progress, MCP badge, and confidence ring

You approve or adjust. The agent executes. You review the outcome the next morning. The agent remembers.

## Architecture

```
User → Flask frontend → Google ADK agent
                              ↓
                        MongoDB MCP server (load-bearing)
                              ↓
                        MongoDB Atlas
                        (sessions, tracks, users, playlists, insights, agent_memory)

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
- **Key integration:** MongoDB MCP server is load-bearing for the agent's nightly Mission. The recommendation query runs through MCP, the query and result are surfaced in the UI with an "MCP" badge, and the agent stores outcomes in MongoDB's `agent_memory` collection to adapt future nights.
- **Beyond chat:** The agent doesn't wait for input — it autonomously plans each night, shows the reasoning in a visual Mission stepper, and learns from review outcomes. You stay in control with approve/swap/regenerate actions.

Apache 2.0 — see [LICENSE](LICENSE)
