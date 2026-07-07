## Goal
- Resolve and fix skill conflicts in the `pi` agent configuration.
- Remove unnecessary third-party skills (`brave-search`).
- Refine project documentation (`README.md` and `HACKATHON.md`) for the Google Cloud Rapid Agent Hackathon submission.
- **Debug and fix the music playback bug on the `/sleep` page** where the audio player fails to play music.
- **Clone and set up StellaAcademy** — a Next.js space-learning app with Ollama worker.

## Constraints & Preferences
- Documentation must be concise, laser-focused, and "anti-AI" (no fluff/marketing speak, no architecture diagrams).
- **Technical**: Investigate frontend-backend data flow, URL resolution, CORS attributes, and browser autoplay policies.
- **StellaAcademy**: TypeScript/Next.js 15 project with Clerk auth, Ollama worker, Google Cloud Tasks, Redis.

## Progress
### Done
- [x] Fixed `brave-search` skill conflicts and removed the directory.
- [x] Rewrote `README.md` and `HACKATHON.md` for hackathon submission.
- [x] Traced playback initialization: `startSleep()` → `POST /api/sleep/plan` → redirect to `/sleep` → `initPlaylist()` → `_queueTrack()` → `_startPlayback()`.
- [x] Verified `data/music/` contains 17 valid OGG/Opus files and `index.json` has matching entries (all files exist on disk).
- [x] Identified that `MONGODB_URI` is not set, causing `get_db()` to return `None` and `get_all_tracks()` to return `[]`.
- [x] Confirmed `list_generated_music()` falls back to `index.json` when MongoDB is disconnected — 17 tracks load correctly with `src="/media/music/<filename>.ogg"`.
- [x] Verified Flask `/media/music/<path:filename>` route and `send_from_directory` serving.
- [x] Analyzed `_startPlayback()` promise rejection handling and gesture unlock flow.
- [x] **Root cause analysis complete**:
  - **Issue 1**: `crossorigin="anonymous"` on `<audio>` element could cause same-origin audio loading failures in some browsers.
  - **Issue 2**: No timeout/error handling in `_queueTrack()` — if `canplay` never fires, audio stays stuck on "Loading...".
  - **Issue 3**: Flask media routes didn't set `Access-Control-Allow-Origin` headers.
- [x] **Fix applied**: Removed `crossorigin="anonymous"`, added `canplay` timeout (10s) with error status, added CORS headers to Flask media routes.
- [x] **StellaAcademy setup**: Cloned repo from `github.com/pixjobs/StellaAcademy`, installed 954 npm packages, created `.env.local`, verified TypeScript compiles and Next.js builds successfully.

### In Progress
- [ ] Test music playback on the sleep page with fixes applied.
- [ ] Configure Clerk keys for StellaAcademy (required for auth, optional for dev).

### Blocked
- (none)

## Key Decisions
- **[Remove brave-search skill]**: Deleted entirely as user indicated no intent to pay/use it.
- **[Documentation Style]**: Dropped verbose tables, AI-generated tone, and architecture diagrams.
- **[Debugging Focus]**: Exhaustive tracing of playback flow from plan page selection through Flask routes to browser audio engine.
- **[StellaAcademy Architecture]**: Next.js 15 web frontend + Node/Express Ollama worker. Auth via Clerk. Cloud Tasks for job queuing. Local dev: web talks directly to worker at `CLOUD_RUN_WORKER_URL`.

## Next Steps
1. **sl33p-space**: Restart Flask server to apply CORS header changes. Test sleep page audio playback.
2. **StellaAcademy**: 
   - Add Clerk keys to `.env.local` (or leave empty — middleware passthroughs if missing).
   - Start web: `cd frontend && npm run dev` (port 3000)
   - Start worker: `npm run worker` (port 8080)
   - Optionally install Ollama (`ollama pull gpt-oss:20b`) for local LLM.
   - Optionally configure Cloud Tasks if using Google Cloud.

## Critical Context
- **sl33p-space**: `/home/yang_pei/sl33p-space` — Flask + Next.js music/sleep app
- **StellaAcademy**: `/home/yang_pei/StellaAcademy` — Next.js space-learning app with Ollama worker
- **Key env vars for Stella**: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `CLOUD_RUN_WORKER_URL`, `OLLAMA_HOST`, `OLLAMA_MODEL`, `DISABLE_AUTH_CHECK`
- **Fixes applied to sl33p-space**:
  1. Removed `crossorigin="anonymous"` from `<audio>` element
  2. Added 10-second `canplay` timeout in `_queueTrack()` with error status message
  3. Flask media routes now set `Access-Control-Allow-Origin: *`
