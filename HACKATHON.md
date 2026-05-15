# Hackathon Submission

**Contest:** Google Cloud Rapid Agent Hackathon  
**Track:** MongoDB  
**Deadline:** June 11, 2026

## What it does

sl33p-space is an AI sleep agent. Describe what you want to sleep to. It generates a track, plans a mood-aware playlist, starts a session, and logs everything in MongoDB. Over time it learns your patterns and recommends better soundscapes.

## How it goes beyond chat

- **Multi-step tool chaining** — A single user action triggers 4–6 tool calls: persona lookup → history query → MongoDB aggregation for insights → track recommendation → session creation.
- **Proactive recommendations** — The agent checks MongoDB sleep history and delivers a personalised plan before the user types anything.
- **Data-driven decisions** — It queries MongoDB aggregation pipelines (avg ratings by track, factor correlation, mood-based performance) to ground recommendations in real data, not LLM intuition.

## MongoDB usage

Five collections: `sleep_sessions`, `users`, `tracks`, `generated_assets`, `packs`.

Key operations:
- `aggregate` with `$group` + `$avg` — per-track quality ratings
- `aggregate` with `$unwind` + `$group` — sleep factor correlations (caffeine, exercise, stress vs. outcomes)
- `aggregate` with `$match` + `$sort` — rating trends and best-performing moods
- `find` + `$sort` — recent session history for recommendations
- `update_one` / `insert_one` — session lifecycle (planned → active → completed → reviewed)

## Agent tools

11 tools: music generation, library browsing, session history, MongoDB aggregation for insights, sleep plan recommendation, session management, persona tracking, tier/credits, and factor logging.

## Tech stack

Gemini + Google ADK + Lyria + MongoDB Atlas + Flask + Firebase Auth + GCS

## Why it fits the MongoDB track

The agent isn't just querying data — it's running aggregation pipelines to reason about what works and taking action. The recommendations, track suggestions, and proactive plans are all grounded in MongoDB analytics.
