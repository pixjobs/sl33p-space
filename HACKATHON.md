# Hackathon Submission Notes

**Contest:** Google Cloud Rapid Agent Hackathon
**Track:** MongoDB
**Deadline:** June 11, 2026

## What sl33p-space does

sl33p-space is a bedtime automation agent. You tell it how you want to sleep — it sets up your nightly routine and handles it autonomously from then on.

The agent generates personalised sleep music with Google's Lyria model, stores tracks in a shared MongoDB library, and learns from your playback history to recommend what works best.

## How it goes beyond chat

1. **Autonomous scheduled execution** — The agent runs your bedtime routine every night at your configured time. No prompt needed. It plays, fades, logs.
2. **Multi-step tool chaining** — "Set up tonight" triggers: profile lookup → history query → track selection → volume setting → schedule creation → confirmation. Five tool calls with reasoning between each.
3. **Proactive pattern surfacing** — The agent notices when tracks are consistently stopped early and suggests alternatives based on completion rates.

## How MongoDB is used

MongoDB is the central data layer, accessed via the official MongoDB MCP server.

| Collection | Purpose |
|---|---|
| `music_library` | Shared Lyria-generated tracks with prompts, tags, play counts, completion rates |
| `users` | Sleep profiles, preferences, generation credits |
| `sleep_sessions` | Playback history — what was played, when, how long, whether completed |
| `routines` | Nightly scheduled routines that execute autonomously |

The agent uses MongoDB MCP tools to query, insert, and aggregate data. Key agentic operations:
- `find` on `sleep_sessions` to analyse which tracks have the best completion rates
- `aggregate` to compute per-user sleep patterns over time
- `insertOne` to log sessions and create routines
- `find` on `music_library` to search shared tracks by tags or popularity

## Tech stack

- **Google ADK** — Multi-agent architecture (root agent + sleep coach sub-agent)
- **Gemini** — Natural language understanding and reasoning
- **Lyria** — AI music generation from text prompts
- **MongoDB Atlas** — Persistent data layer via MCP
- **Flask** — Web interface
- **Cloud Run** — Hosting

## Judging criteria

| Criterion | How sl33p-space delivers |
|---|---|
| **Technological Implementation** | ADK multi-agent, MongoDB MCP, Lyria generation, browser audio with fade, Cloud Run deployment |
| **Design** | Dark space-themed UI, mobile-first, natural language as primary interface, set-and-forget UX |
| **Potential Impact** | Sleep affects everyone. Personalised bedtime automation is universally useful. Shared library scales. |
| **Quality of the Idea** | AI-generated personalised sleep music + autonomous bedtime agent. Not another RAG chatbot. |
