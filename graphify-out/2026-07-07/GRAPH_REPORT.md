# Graph Report - sl33p-space  (2026-07-07)

## Corpus Check
- 49 files · ~96,363 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 610 nodes · 1374 edges · 42 communities (40 shown, 2 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 88 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `cf654234`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_music_gen.py|music_gen.py]]
- [[_COMMUNITY_plan.js|plan.js]]
- [[_COMMUNITY_get_db|get_db]]
- [[_COMMUNITY_agent.py|agent.py]]
- [[_COMMUNITY_test_visibility.py|test_visibility.py]]
- [[_COMMUNITY_test_agent.py|test_agent.py]]
- [[_COMMUNITY_playlist.py|playlist.py]]
- [[_COMMUNITY_Bugs Found (in severity order)|Bugs Found (in severity order)]]
- [[_COMMUNITY_api|api]]
- [[_COMMUNITY_app.py|app.py]]
- [[_COMMUNITY_sessions.py|sessions.py]]
- [[_COMMUNITY_experiments.py|experiments.py]]
- [[_COMMUNITY_player.js|player.js]]
- [[_COMMUNITY_get_recommendation|get_recommendation]]
- [[_COMMUNITY__get_user|_get_user]]
- [[_COMMUNITY_list_generated_music|list_generated_music]]
- [[_COMMUNITY_log_api_usage|log_api_usage]]
- [[_COMMUNITY_sl33p-space|sl33p-space]]
- [[_COMMUNITY_app.js|app.js]]
- [[_COMMUNITY_auth.js|auth.js]]
- [[_COMMUNITY__el|_el]]
- [[_COMMUNITY_assets.py|assets.py]]
- [[_COMMUNITY_music.js|music.js]]
- [[_COMMUNITY_Hackathon Submission|Hackathon Submission]]
- [[_COMMUNITY_summary|summary.md]]
- [[_COMMUNITY_users.py|users.py]]
- [[_COMMUNITY_get_user_sleep_insights|get_user_sleep_insights]]
- [[_COMMUNITY_admin.py|admin.py]]
- [[_COMMUNITY_packs.py|packs.py]]
- [[_COMMUNITY__build_plan_trace|_build_plan_trace]]
- [[_COMMUNITY__make_genai_mock|_make_genai_mock]]
- [[_COMMUNITY_test_experiments.py|test_experiments.py]]
- [[_COMMUNITY_labGenerate|labGenerate]]
- [[_COMMUNITY_build_coach_checkin|build_coach_checkin]]
- [[_COMMUNITY_add_memory|add_memory]]
- [[_COMMUNITY_test_lyria_gen.py|test_lyria_gen.py]]
- [[_COMMUNITY_get_recent_sessions|get_recent_sessions]]
- [[_COMMUNITY_deploy.sh|deploy.sh]]

## God Nodes (most connected - your core abstractions)
1. `get_db()` - 115 edges
2. `create_app()` - 92 edges
3. `api()` - 36 edges
4. `showToast()` - 33 edges
5. `generate_music()` - 28 edges
6. `get_recommendation()` - 19 edges
7. `_get_user()` - 16 edges
8. `build_playlist()` - 14 edges
9. `get_user_sleep_insights()` - 12 edges
10. `list_generated_music()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `test_visibility_endpoint()` --calls--> `create_app()`  [EXTRACTED]
  tests/test_visibility.py → web/app.py
- `test_visibility_endpoint_rejects_invalid()` --calls--> `create_app()`  [EXTRACTED]
  tests/test_visibility.py → web/app.py
- `generate_music_track()` --calls--> `generate_music()`  [EXTRACTED]
  agent/agent.py → audio/music_gen.py
- `get_mongodb_sleep_insights()` --calls--> `get_user_sleep_insights()`  [EXTRACTED]
  agent/agent.py → db/insights.py
- `recommend_sleep_plan()` --calls--> `list_generated_music()`  [EXTRACTED]
  agent/agent.py → audio/music_gen.py

## Import Cycles
- None detected.

## Communities (42 total, 2 thin omitted)

### Community 0 - "music_gen.py"
Cohesion: 0.06
Nodes (73): _bucket_name(), delete_from_gcs(), _get_client(), get_gcs_info(), get_signed_url(), get_track_url(), is_gcs_enabled(), Google Cloud Storage integration for sl33p-space music tracks.  Enabled when GCS (+65 more)

### Community 1 - "plan.js"
Cohesion: 0.08
Nodes (20): _applyAgentTrack(), changeTrack(), labBack(), _labBuildPreview(), _labBuildPrompt(), labNext(), labSelectColour(), labSelectTheme() (+12 more)

### Community 2 - "get_db"
Cohesion: 0.17
Nodes (25): update_playlist_progress(), get_random_scene(), get_recent_feedback(), submit_feedback(), get_db(), get_all_packs(), add_credits(), award_sleep_bonus() (+17 more)

### Community 3 - "agent.py"
Cohesion: 0.09
Nodes (24): create_runner(), get_user_feedback(), _get_verify_runner(), _load_agent_config(), log_factors(), _parse_verify_text(), sl33p-space agent built with Google ADK.  When GOOGLE_API_KEY is set, this provi, Set the current user's sleep persona.      Args:         persona_key: One of: sh (+16 more)

### Community 4 - "test_visibility.py"
Cohesion: 0.10
Nodes (24): list_archived_music(), Format a MongoDB track document for API responses., List all archived music tracks., _track_entry(), get_all_tracks(), get_public_tracks(), set_track_visibility(), Tests for track visibility, tester tier, and scoped track access. (+16 more)

### Community 5 - "test_agent.py"
Cohesion: 0.11
Nodes (24): _deterministic_pick(), _predict_outcome(), Pick a track and write a fallback reasoning line from MongoDB data alone., Predict tonight's rating from the mood×track cell, or describe the exploration s, _mock_db(), Tests for agent consolidation: contextvars threading, deterministic helpers, get, Brand-new user: no best_track, no matrix, just pick first available., No tracks at all — title should be None, no crash. (+16 more)

### Community 6 - "playlist.py"
Cohesion: 0.13
Nodes (22): build_playlist(), complete_playlist(), get_playlist(), _get_recent_track_ids(), _get_user_track_history(), _pick_best(), _pick_by_energy(), _pick_by_id() (+14 more)

### Community 7 - "Bugs Found (in severity order)"
Cohesion: 0.08
Nodes (23): BUG-1 (Critical): Experiment data destroyed on "Skip Review", BUG-2 (Critical): `_resolveTrack()` returns wrong track after mood change, BUG-3 (High): `_plan.mood` silently set to `'calm'` on load, overwriting agent recommendation, BUG-4 (High): Swap track only cycles by title — can swap to wrong track or silently fail, BUG-5 (Medium): `_refreshTrackList` is referenced but not defined, BUG-6 (Medium): Agent rec page-load hangs on MCP verification, BUG-7 (Medium): Coach check-in can show duplicate/conflicting messages, BUG-8 (Low): `_build_prompt` experiment section has stale `active` state (+15 more)

### Community 8 - "api"
Cohesion: 0.16
Nodes (23): api(), showToast(), archiveTrack(), deleteTrack(), unarchiveTrack(), acceptExperiment(), ackExperiment(), copyReferralLink() (+15 more)

### Community 9 - "app.py"
Cohesion: 0.15
Nodes (19): format_track_entry(), get_preset_prompts(), set_admin(), get_generation_job(), update_generation_job(), _enqueue_music_task(), rate_limit(), Simple in-memory per-user rate limiter. (+11 more)

### Community 10 - "sessions.py"
Cohesion: 0.14
Nodes (21): _auto_complete_stale(), cleanup_stale_sessions(), clear_stale_reviews(), create_manual_session(), create_session(), delete_session(), end_session(), _force_complete_active() (+13 more)

### Community 11 - "experiments.py"
Cohesion: 0.16
Nodes (18): accept_experiment(), acknowledge_experiment(), decline_experiment(), _factor_baseline(), _finalize(), get_active_experiment(), ObjectId, propose_experiment() (+10 more)

### Community 12 - "player.js"
Cohesion: 0.27
Nodes (15): addToQueue(), _audio(), clearQueue(), _drawVisualizer(), _initVisualizer(), _loadAndPlay(), playerNext(), playerPrev() (+7 more)

### Community 13 - "get_recommendation"
Cohesion: 0.13
Nodes (15): _build_mission(), _fallback_handler(), get_mongodb_sleep_insights(), get_recommendation(), Keyword-based handler when ADK is not available — still data-rich., Recommend a sleep plan with a mood-aware playlist.      Args:         mood: Curr, The visible 'mission' the agent plans and executes — a beyond-chat,     watch-it, Generate a rich sleep recommendation: deterministic plan + one Gemini call. (+7 more)

### Community 14 - "_get_user"
Cohesion: 0.15
Nodes (15): generate_music_track(), get_tracking_level(), _get_user(), get_user_tier_info(), Get the user's data tracking preference (minimal, basic, or detailed)., Get the current user's subscription tier, credits, and generation allowance., Generate a unique sleep music track using AI (Lyria).      Args:         prompt:, _set_user() (+7 more)

### Community 15 - "list_generated_music"
Cohesion: 0.15
Nodes (13): _build_prompt(), get_user_persona(), list_music_library(), Start a sleep session with a mood-aware playlist and return the URL.      Args:, Get the current user's sleep persona and what it means.      Returns:         Pe, List all AI-generated music tracks in the library., Build the root prompt with persona context injected., start_sleep_session() (+5 more)

### Community 16 - "log_api_usage"
Cohesion: 0.21
Nodes (9): make_chat_handler(), prewarm_mcp(), Eagerly initialise the MCP verifier so the first /plan load isn't slow.      Cal, Return a function that handles chat messages via ADK or fallback., get_global_usage(), get_user_usage(), log_api_usage(), create_app() (+1 more)

### Community 17 - "sl33p-space"
Cohesion: 0.17
Nodes (11): Architecture, Deploy, Features, Hackathon context, How it goes beyond chat, Project structure, Run locally, sl33p-space (+3 more)

### Community 18 - "app.js"
Cohesion: 0.24
Nodes (8): _renderMd(), submitGeneralFeedback(), toggleFeedbackWidget(), _addChatRow(), sendChat(), _updateChatCounter(), _autoGreetChat(), toggleAgentChat()

### Community 19 - "auth.js"
Cohesion: 0.29
Nodes (9): _ensureGsi(), _gsiButtonFallback(), _handleGsiCredential(), _hideAuthLoading(), _showAuthLoading(), signInWithEmail(), signInWithGoogle(), _signOutAndGoHome() (+1 more)

### Community 20 - "_el"
Cohesion: 0.27
Nodes (12): _el(), _expActiveCard(), _expCard(), _expCompletedCard(), _expProposedCard(), _missionStepEl(), regenerateAgentPlan(), _renderAgentRec() (+4 more)

### Community 21 - "assets.py"
Cohesion: 0.38
Nodes (9): cache_apod(), cache_scene_image(), get_apod_pool(), get_cached_apod(), get_latest_apod(), get_scene_pool_size(), generate_scene_image(), get_apod() (+1 more)

### Community 22 - "music.js"
Cohesion: 0.35
Nodes (10): _createTrackRow(), generateCustom(), generateFromPreset(), generateMusic(), inspireMe(), _pollJob(), _refreshTrackList(), suggestVariation() (+2 more)

### Community 23 - "Hackathon Submission"
Cohesion: 0.20
Nodes (9): Agent tools, Hackathon Submission, How it goes beyond chat, Mission architecture (cheap + grounded), MongoDB usage, Tech stack, The real-world challenge, What it does (+1 more)

### Community 24 - "summary.md"
Cohesion: 0.20
Nodes (9): Blocked, Constraints & Preferences, Critical Context, Done, Goal, In Progress, Key Decisions, Next Steps (+1 more)

### Community 25 - "users.py"
Cohesion: 0.28
Nodes (8): get_user(), get_user_quota(), increment_generation_count(), Get user's generation quota and current count., Increment the user's generation count. Returns False if quota exceeded., update_preferences(), update_timezone(), upsert_user()

### Community 26 - "get_user_sleep_insights"
Cohesion: 0.36
Nodes (7): Any, _default_insights(), _extract_note_keyword(), get_user_sleep_insights(), Return the most-mentioned content keyword across notes, if ≥3 mentions., Return MongoDB-backed sleep insights for a user.      This keeps the hackathon i, _round()

### Community 27 - "admin.py"
Cohesion: 0.39
Nodes (7): _empty_stats(), get_platform_stats(), get_track_list(), get_usage_summary(), get_user_list(), _pseudonymise_email(), resolve_track_url()

### Community 28 - "packs.py"
Cohesion: 0.39
Nodes (7): create_pack(), get_pack(), ObjectId, purchase_pack(), Music packs — curated bundles of tracks users can purchase with credits., Purchase a pack with credits. Returns pack info or error., user_owns_pack()

### Community 29 - "_build_plan_trace"
Cohesion: 0.29
Nodes (7): _build_plan_trace(), Construct the agent's reasoning trace from pre-computed MongoDB data.      Free, No reviewed sessions yet — trace should call it out and still produce steps., Challenging factor below 3.5 should generate a 'considered factors' step., test_build_plan_trace_factor_warning(), test_build_plan_trace_first_night(), test_build_plan_trace_mood_match_appears()

### Community 30 - "_make_genai_mock"
Cohesion: 0.33
Nodes (6): _make_genai_mock(), Create a mock genai module with a preset response., Valid Gemini synthesis JSON populates vibe/reasoning/confidence; track stays det, Confidence values outside [0,1] should be clamped., test_get_recommendation_clamps_confidence(), test_get_recommendation_gemini_success()

### Community 32 - "labGenerate"
Cohesion: 0.53
Nodes (6): _labBuildTitle(), labGenerate(), _labPollJob(), _labResetGenUI(), _labShowResult(), _refreshTrackList()

### Community 33 - "build_coach_checkin"
Cohesion: 0.40
Nodes (5): build_coach_checkin(), A warm, time-aware coach line that reflects where the user is right now:     a p, get_recent_completed_experiment(), A completed experiment the user hasn't acknowledged yet (to report once)., get_pending_review()

### Community 34 - "add_memory"
Cohesion: 0.40
Nodes (4): add_memory(), ObjectId, Store a memory for the agent to recall when building recommendations.      Args:, str

### Community 35 - "test_lyria_gen.py"
Cohesion: 0.60
Nodes (4): _direct_test(), _print_result(), Unit test for Lyria music generation. Uses a temp folder so no pollution of actu, run_test()

### Community 37 - "get_recent_sessions"
Cohesion: 0.50
Nodes (4): get_sleep_history(), Get the current user's recent sleep sessions and stats.      Args:         limit, get_recent_sessions(), get_sleep_stats()

## Knowledge Gaps
- **47 isolated node(s):** `deploy.sh script`, `The real-world challenge`, `What it does`, `How it goes beyond chat`, `Mission architecture (cheap + grounded)` (+42 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_db()` connect `get_db` to `music_gen.py`, `build_coach_checkin`, `add_memory`, `agent.py`, `test_visibility.py`, `get_recent_sessions`, `playlist.py`, `app.py`, `sessions.py`, `experiments.py`, `list_generated_music`, `log_api_usage`, `assets.py`, `users.py`, `get_user_sleep_insights`, `admin.py`, `packs.py`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._
- **Why does `create_app()` connect `get_db` to `music_gen.py`, `agent.py`, `test_visibility.py`, `test_agent.py`, `playlist.py`, `app.py`, `sessions.py`, `experiments.py`, `get_recommendation`, `list_generated_music`, `log_api_usage`, `assets.py`, `users.py`, `get_user_sleep_insights`, `admin.py`, `packs.py`, `build_coach_checkin`, `add_memory`, `get_recent_sessions`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Why does `generate_music()` connect `music_gen.py` to `get_db`, `agent.py`, `test_visibility.py`, `app.py`, `_get_user`, `log_api_usage`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Are the 33 inferred relationships involving `api()` (e.g. with `_signOutAndGoHome()` and `sendChat()`) actually correct?**
  _`api()` has 33 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `showToast()` (e.g. with `_ensureGsi()` and `_handleGsiCredential()`) actually correct?**
  _`showToast()` has 30 INFERRED edges - model-reasoned connections that need verification._
- **What connects `sl33p-space agent built with Google ADK.  When GOOGLE_API_KEY is set, this provi`, `Generate a unique sleep music track using AI (Lyria).      Args:         prompt:`, `List all AI-generated music tracks in the library.` to the rest of the system?**
  _164 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `music_gen.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05827505827505827 - nodes in this community are weakly interconnected._