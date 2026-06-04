# Hackathon Submission

**Contest:** Building Agents for Real-World Challenges
**Track:** MongoDB
**Deadline:** June 11, 2026

## The real-world challenge

Poor sleep is a chronic health problem, and it falls hardest on people with irregular or high-stress schedules — shift workers, emergency-services staff, light sleepers, insomniacs (each a built-in persona that changes how the agent plans). Generic sleep apps give you a static library and leave every decision to you. sl33p-space makes those decisions an agent's job: reason over the user's own logged outcomes, plan and execute a multi-step nightly routine, keep the audio unbroken until morning, and adapt from the result. The music is the medium; the agent is the product.

## What it does

sl33p-space is an agentic sleep companion. Every night when you open `/plan`, the agent autonomously builds a plan before you say anything: analyses your sleep history via MongoDB MCP, selects a track, composes a continuous overnight arc, predicts the outcome, and surfaces the reasoning in a visual Mission stepper. You approve or adjust. The agent executes. You review the outcome. The agent remembers what worked and adapts future nights.

## How it goes beyond chat

**Autonomous nightly Mission (the "beyond chat" surface)**

When you open `/plan`, the agent doesn't wait for input. It runs a six-step Mission, visible as an animated stepper with numbered progress:

1. **Analyse history** — Aggregates MongoDB session data: recent nights, mood × track matrix, factor correlations
2. **Verify via MCP (load-bearing)** — Runs a MongoDB query through the MCP server to check average ratings for the chosen track under current conditions. The query and result are surfaced in the UI with an "MCP" badge.
3. **Choose track** — Selects the best track from your library based on mood, persona, and past outcomes
4. **Compose continuous arc** — Builds a seamless settling → transition → deep-sleep playlist stitched into one infinitely-looping source (no more mid-night audio cutoffs)
5. **Predict outcome** — Estimates rating and confidence from historical data, displayed in a confidence ring
6. **Ready** — Shows approve/swap/regenerate actions. You stay in control.

The Mission is the agent's visible, watch-it-work surface. No chat needed.

**Close-the-loop agent memory**

After each session you rate how it went. The agent records the outcome in MongoDB's `agent_memory` collection and cites what worked on the next night's recommendation. The loop: plan → execute → review → adapt → plan better.

**Personable coach + multi-night experiments**

A consistent coach (Nova) checks in each visit — reviewing last night, recalling what worked, and keeping a warm, familiar tone rather than acting like a generic chatbot. Its agentic core is the experiment engine: when your MongoDB factor correlations suggest a lever (e.g. caffeine nights average 2.5/5 versus 4.0/5 without), the coach proposes an opt-in N-night experiment, tracks adherence and ratings as you review each night, then aggregates the result and reports a verdict. This is a genuine plan → execute-over-days → measure → adapt loop — something a chatbot can't do — and it runs purely on MongoDB, with no per-night LLM or music-generation cost. New collection: `sleep_experiments`.

**Tool-using chat agent (ADK)** — When you do chat, the agent has 12 tools chaining across MongoDB collections, music generation, and session lifecycle.

## Mission architecture (cheap + grounded)

The `/plan` page hits one endpoint, which runs:

1. **Deterministic phase (no LLM):** MongoDB aggregations → insights → playlist build → track pick → continuous arc stitch → outcome prediction → Mission steps
2. **MongoDB MCP verification (load-bearing):** The agent queries MongoDB via the MCP server to verify the chosen track's average rating under current conditions. The query is real: `db.sleep_sessions.aggregate([{$match: {track_id, mood, 'review.rating': {$exists: true}}}, {$group: {_id: null, avg_rating: {$avg: '$review.rating'}}}])`. Result and query text are surfaced in the Mission stepper with an "MCP" badge.
3. **Single structured Gemini call:** With everything pre-decided, one `gemini-3-flash-preview` call with a Pydantic `response_schema` produces the creative synthesis — a 4–8 word vibe caption and a one-sentence reasoning grounded in real numbers.

Result: ~200 output tokens per recommendation, no parsing failures, and the track choice stays grounded in MongoDB data rather than LLM intuition.

## MongoDB usage

Seven collections: `sleep_sessions`, `users`, `tracks`, `generated_assets`, `packs`, `agent_memory`, `sleep_experiments`.

Key operations driving the agent:
- `aggregate` with `$group` + `$avg` — per-track quality ratings (load-bearing for MCP verification query)
- `aggregate` with `$unwind` + `$group` — sleep factor correlations (caffeine, exercise, stress vs. outcomes)
- `aggregate` with `$match` + `$sort` — rating trends, best-performing moods, mood × track matrix
- `find` + `$sort` — recent session history for Mission step 1
- `update_one` / `insert_one` — session lifecycle (planned → active → completed → reviewed)
- `insert_one` into `agent_memory` — stores outcome learnings after each review
- `aggregate` with `$in` + `$group` over `sleep_experiments` — baseline avg rating with vs without a factor, driving the experiment proposal and verdict

The mood × track matrix and factor correlations directly drive the track pick and Mission reasoning. The MCP query verifies the choice against real session data.

## Agent tools

12 ADK tools available to the chat agent: music generation, library browsing, session history, MongoDB aggregation for insights, sleep plan recommendation (calls the Mission endpoint), session management, persona tracking, tier/credits, factor logging, and user feedback.

## Tech stack

Google ADK + Gemini 3 Flash + Lyria 3 Pro + MongoDB Atlas + MongoDB MCP server (load-bearing) + Flask + Firebase Auth + GCS + Cloud Run

## Why it fits the MongoDB track

The MongoDB MCP server is load-bearing: the nightly Mission runs a real aggregation query via MCP to verify the track choice, the query is surfaced in the UI with an "MCP" badge, and outcomes are stored in MongoDB's `agent_memory` collection to adapt future nights. Every recommendation cites real numbers from MongoDB aggregation pipelines. The track choice is deterministic from history; the LLM only does creative framing. The agent's work is visible, grounded, and closed-loop.
