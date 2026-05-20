# Hackathon Submission

**Contest:** Google Cloud Rapid Agent Hackathon
**Track:** MongoDB
**Deadline:** June 11, 2026

## What it does

sl33p-space is an AI sleep agent. Describe what you want to sleep to. It generates a track with Lyria, plans a mood-aware playlist, starts a session, and logs everything in MongoDB. Over time it learns your patterns and recommends better soundscapes.

## How it goes beyond chat

- **Proactive recommendation on page load** — The agent runs every time the user opens `/plan`. Before any input, it pulls MongoDB sleep history, builds a sleep arc (settling → transition → deep_sleep), and synthesises a recommendation. No chat required.
- **Visible reasoning trace** — The plan card surfaces a numbered "How I picked this" trace showing the actual MongoDB steps: sessions pulled, mood × track matrix consulted, lifestyle factors weighed, optimal sleep window, arc built, track chosen. The agent's work is observable, not a black box.
- **Predicted outcome + confidence** — Each recommendation includes a rating prediction grounded in the mood × track cell from MongoDB, plus a confidence score reflecting data depth.
- **Tool-using chat agent (ADK)** — When the user does chat, the ADK agent has 12 tools that chain across MongoDB collections, music generation, and session lifecycle.

## Recommendation architecture (cheap + rich)

The `/plan` page hits one endpoint, which runs:

1. **Deterministic phase (no LLM):** MongoDB aggregations → insights → playlist build → track pick → reasoning trace → outcome prediction.
2. **Single structured Gemini call:** With everything pre-decided, one `gemini-3-flash-preview` call with a Pydantic `response_schema` produces the creative synthesis — a 4–8 word vibe caption, a one-sentence reasoning grounded in real numbers, and a confidence score.

Result: ~200 output tokens per recommendation, no parsing failures, and the track choice stays grounded in MongoDB data rather than LLM intuition.

## MongoDB usage

Five collections: `sleep_sessions`, `users`, `tracks`, `generated_assets`, `packs`.

Key operations driving the agent:
- `aggregate` with `$group` + `$avg` — per-track quality ratings
- `aggregate` with `$unwind` + `$group` — sleep factor correlations (caffeine, exercise, stress vs. outcomes)
- `aggregate` with `$match` + `$sort` — rating trends, best-performing moods, mood × track matrix
- `find` + `$sort` — recent session history
- `update_one` / `insert_one` — session lifecycle (planned → active → completed → reviewed)

The mood × track matrix and factor correlations directly drive both the deterministic track pick and the trace that's surfaced in the UI.

## Agent tools

12 ADK tools available to the chat agent: music generation, library browsing, session history, MongoDB aggregation for insights, sleep plan recommendation, session management, persona tracking, tier/credits, factor logging, and user feedback.

## Tech stack

Google ADK + Gemini 3 Flash Preview + Lyria 3 Pro + MongoDB Atlas (+ MCP server) + Flask + Firebase Auth + GCS + Cloud Run

## Why it fits the MongoDB track

The agent isn't just querying data — it's running aggregation pipelines to reason about what works, and exposing that reasoning to the user. Every recommendation cites a real number from MongoDB. The track choice is deterministic from history; the LLM only does the creative framing.
