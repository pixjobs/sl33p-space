"""
sl33p-space agent built with Google ADK.

When GOOGLE_API_KEY is set, this provides a Gemini-powered sleep assistant.
When not set, it falls back to a data-driven handler so the app
still works without an API key during development.
"""

import contextvars
import json
import os
from typing import Optional

from agent.prompts import ROOT_PROMPT, PERSONA_CONTEXTS

_adk_available = False
_root_agent = None

# Thread-safe user context — each request gets its own value.
_user_ctx = contextvars.ContextVar("user_id", default="default")

try:
    from google.adk.agents import Agent
    from google.adk.runners import InMemoryRunner
    from google.genai import types as genai_types
    _adk_available = True
except ImportError:
    _adk_available = False


VALID_PERSONAS = ["shift_worker", "emergency_services", "shallow_sleeper", "insomniac"]
VALID_FACTORS = ["caffeine", "exercise", "screen_time", "stress", "alcohol", "nap", "late_meal"]


def _set_user(uid: str):
    _user_ctx.set(uid)


def _get_user() -> str:
    return _user_ctx.get()


# --- Tool functions (called by Gemini) ---

def generate_music_track(prompt: str) -> dict:
    """Generate a unique sleep music track using AI (Lyria).

    Args:
        prompt: Description of the music to generate (e.g. "gentle ambient with soft rain textures").

    Returns:
        Path to the generated audio file, or error message.
    """
    from audio.music_gen import generate_music
    return generate_music(prompt, user_id=_get_user())


def list_music_library() -> dict:
    """List all AI-generated music tracks in the library."""
    from audio.music_gen import list_generated_music
    return {"tracks": list_generated_music()}


def get_sleep_history(limit: int = 7) -> dict:
    """Get the current user's recent sleep sessions and stats.

    Args:
        limit: Number of recent sessions to return (default 7).

    Returns:
        Recent sessions with ratings, durations, factors, and overall stats.
    """
    from db.sessions import get_recent_sessions, get_sleep_stats
    uid = _get_user()
    sessions = get_recent_sessions(uid, limit=limit)
    stats = get_sleep_stats(uid)
    formatted = []
    for s in sessions:
        review = s.get("review") or {}
        formatted.append({
            "track": s.get("plan", {}).get("soundscape_title", "Unknown"),
            "mood": s.get("plan", {}).get("mood", ""),
            "duration_minutes": round(s.get("actual", {}).get("duration_minutes", 0), 1),
            "rating": review.get("rating"),
            "factors": review.get("factors", []),
        })
    return {"recent_sessions": formatted, "stats": stats}


def get_mongodb_sleep_insights(days: int = 30) -> dict:
    """Analyze the current user's MongoDB sleep history.

    Args:
        days: Lookback window in days for sessions, ratings, tracks, and factors.

    Returns:
        MongoDB-backed insights including best tracks, mood patterns, factor correlations, and recommendation summary.
    """
    from db.insights import get_user_sleep_insights
    return get_user_sleep_insights(_get_user(), days=days)


def recommend_sleep_plan(mood: str = "calm") -> dict:
    """Recommend a sleep plan with a mood-aware playlist.

    Args:
        mood: Current mood (wired, stressed, restless, tired, calm).

    Returns:
        Recommended sleep plan with playlist tracks and reasoning context.
    """
    from audio.music_gen import list_generated_music
    from audio.playlist import build_playlist
    from db.sessions import get_recent_sessions, get_sleep_stats
    from db.users import get_persona

    uid = _get_user()
    tracks = list_generated_music()
    stats = get_sleep_stats(uid)
    persona = get_persona(uid)
    insights = get_mongodb_sleep_insights()
    if mood == "calm" and insights.get("recommended_mood"):
        mood = insights["recommended_mood"]

    playlist_data = build_playlist(mood, persona, uid)
    playlist_tracks = []
    if playlist_data:
        playlist_tracks = [
            {"title": t["title"], "role": t["role"], "energy": t.get("energy_level")}
            for t in playlist_data.get("tracks", [])
        ]

    best_rated = None
    for s in get_recent_sessions(uid, limit=7):
        r = (s.get("review") or {}).get("rating", 0)
        if r >= 4:
            best_rated = s.get("plan", {}).get("soundscape_title")
            break

    return {
        "available_tracks": [t["title"] for t in tracks],
        "playlist_preview": playlist_tracks,
        "playlist_id": playlist_data.get("playlist_id") if playlist_data else None,
        "total_sessions": stats.get("total_sessions", 0),
        "avg_rating": stats.get("avg_rating"),
        "top_sound": stats.get("top_sound") or best_rated,
        "mood": mood,
        "persona": persona,
        "mongodb_insights": insights,
    }


def start_sleep_session(track_title: str = "", mood: str = "calm") -> dict:
    """Start a sleep session with a mood-aware playlist and return the URL.

    Args:
        track_title: Title of a preferred track. Playlist will still be built around mood.
        mood: User's current mood.

    Returns:
        Dict with redirect_url for the sleep page, or error.
    """
    from audio.music_gen import list_generated_music
    from audio.playlist import build_playlist
    from db.sessions import create_session
    from db.users import get_persona

    uid = _get_user()
    tracks = list_generated_music()
    persona = get_persona(uid)

    preferred_id = None
    if track_title:
        for t in tracks:
            if t["title"].lower() == track_title.lower():
                preferred_id = t.get("id")
                break

    playlist_data = build_playlist(mood, persona, uid,
                                   preferred_track_id=preferred_id)
    playlist_id = playlist_data.get("playlist_id") if playlist_data else None

    if playlist_data and playlist_data.get("tracks"):
        first = playlist_data["tracks"][0]
        plan = {
            "soundscape_id": first.get("track_id"),
            "soundscape_title": first.get("title"),
            "soundscape_src": first.get("src"),
            "duration_target_hours": 7.5,
            "wind_down": "4-7-8 breathing",
            "mood": mood,
        }
    else:
        selected = None
        for t in tracks:
            if track_title and t["title"].lower() == track_title.lower():
                selected = t
                break
        if not selected and tracks:
            selected = tracks[0]
        plan = {
            "soundscape_id": selected["id"] if selected else None,
            "soundscape_title": selected["title"] if selected else "Ambient",
            "soundscape_src": selected.get("src") if selected else None,
            "duration_target_hours": 7.5,
            "wind_down": "4-7-8 breathing",
            "mood": mood,
        }

    session_id = create_session(uid, plan, playlist_id=playlist_id)
    if not session_id:
        return {"error": "Could not create session"}

    params = [f"session={session_id}"]
    if playlist_id:
        params.append(f"playlist={playlist_id}")
    if plan["soundscape_src"]:
        params.append(f"track={plan['soundscape_src']}")
    if plan["soundscape_title"]:
        params.append(f"title={plan['soundscape_title']}")

    track_list = [t["title"] for t in playlist_data.get("tracks", [])] if playlist_data else [plan["soundscape_title"]]

    return {
        "redirect_url": "/sleep?" + "&".join(params),
        "session_id": session_id,
        "tracks": track_list,
    }


def get_user_persona() -> dict:
    """Get the current user's sleep persona and what it means.

    Returns:
        Persona key, label, and description. Or null if no persona set.
    """
    from db.users import get_persona
    persona = get_persona(_get_user())
    if persona and persona in PERSONA_CONTEXTS:
        labels = {
            "shift_worker": "Shift Worker",
            "emergency_services": "Emergency Services",
            "shallow_sleeper": "Shallow Sleeper",
            "insomniac": "Insomniac",
        }
        return {
            "persona": persona,
            "label": labels.get(persona, persona),
            "context": PERSONA_CONTEXTS[persona],
        }
    return {"persona": None, "label": "None set", "context": ""}


def set_user_persona(persona_key: str) -> dict:
    """Set the current user's sleep persona.

    Args:
        persona_key: One of: shift_worker, emergency_services, shallow_sleeper, insomniac.
                     Pass empty string to clear.

    Returns:
        Confirmation of the persona set.
    """
    from db.users import set_persona
    if persona_key and persona_key not in VALID_PERSONAS:
        return {"error": f"Invalid persona. Choose from: {VALID_PERSONAS}"}
    set_persona(_get_user(), persona_key or None)
    return {"set": persona_key or None}


def get_tracking_level() -> dict:
    """Get the user's data tracking preference (minimal, basic, or detailed)."""
    from db.users import get_user
    user = get_user(_get_user())
    if user:
        level = user.get("preferences", {}).get("tracking_level", "basic")
        return {"tracking_level": level}
    return {"tracking_level": "basic"}


def get_user_tier_info() -> dict:
    """Get the current user's subscription tier, credits, and generation allowance.

    Returns:
        Tier type, trial status, credits balance, and whether they can generate tracks.
    """
    from db.tiers import get_user_tier
    return get_user_tier(_get_user())


def log_factors(session_id: str, factors: str) -> dict:
    """Log lifestyle factors for a sleep session.

    Args:
        session_id: The session ID to log factors for.
        factors: Comma-separated factors from: caffeine, exercise, screen_time, stress, alcohol, nap, late_meal.

    Returns:
        Confirmation.
    """
    from db.sessions import update_session_factors
    factor_list = [f.strip() for f in factors.split(",") if f.strip()]
    valid = [f for f in factor_list if f in VALID_FACTORS]
    if update_session_factors(session_id, valid):
        return {"logged": valid}
    return {"error": "Could not update session"}


def get_user_feedback(limit: int = 5) -> dict:
    """Get recent feedback from the current user to understand their experience.

    Args:
        limit: Number of recent feedback items to return (default 5).

    Returns:
        Recent feedback items and counts by type (thumbs_up, thumbs_down, bug, idea).
    """
    from db.feedback import get_user_feedback_summary
    return get_user_feedback_summary(_get_user(), limit=limit)


ROOT_TOOLS = [
    get_sleep_history,
    get_mongodb_sleep_insights,
    recommend_sleep_plan,
    start_sleep_session,
    generate_music_track,
    list_music_library,
    get_user_persona,
    set_user_persona,
    get_tracking_level,
    get_user_tier_info,
    log_factors,
    get_user_feedback,
]


# --- Structured recommendation (used by /api/sleep/recommend) ---
#
# Architecture: agent runs every time the plan page loads. To stay cheap we
# *pre-compute* everything we deterministically can (insights, playlist,
# candidate trace), then make a single Gemini call with a tight JSON schema
# for the creative bits (vibe, reasoning, predicted outcome). One call per
# page load, ~200 output tokens, structured output prevents parsing failures.


def _build_plan_trace(insights: dict, playlist_preview: list, mood: str,
                      chosen_title: str | None) -> list[dict]:
    """Construct the agent's reasoning trace from pre-computed MongoDB data.

    Free (no LLM tokens) and gives the UI something to render that makes the
    agent feel like it actually walked through the data instead of guessing.
    """
    trace = []
    stats = insights.get("stats", {}) or {}
    reviewed = stats.get("reviewed_sessions", 0)

    if reviewed:
        avg = stats.get("avg_rating")
        trace.append({
            "step": "Pulled sleep history",
            "detail": f"{reviewed} reviewed nights, avg {avg or '?'}/5 from MongoDB",
        })
    else:
        trace.append({
            "step": "Pulled sleep history",
            "detail": "First night — no prior data yet, exploring",
        })

    matrix = insights.get("mood_track_matrix", []) or []
    mood_hit = next((m for m in matrix if m.get("mood") == mood), None)
    if mood_hit:
        trace.append({
            "step": f"Cross-referenced mood × track for '{mood}'",
            "detail": (f"{mood_hit['track']} leads at {mood_hit['avg_rating']}/5 "
                       f"across {mood_hit['sessions']} sessions"),
        })
    elif matrix:
        top = matrix[0]
        trace.append({
            "step": "Checked mood × track matrix",
            "detail": (f"No '{mood}' history yet — best overall pairing is "
                       f"{top['track']} when {top['mood']} ({top['avg_rating']}/5)"),
        })

    best_factor = insights.get("best_factor")
    worst_factor = insights.get("challenging_factor")
    if worst_factor and worst_factor.get("avg_rating") and worst_factor["avg_rating"] < 3.5:
        trace.append({
            "step": "Considered lifestyle factors",
            "detail": (f"{worst_factor['factor'].replace('_', ' ').title()} drags your "
                       f"sleep to {worst_factor['avg_rating']}/5 — favoring deeper arc"),
        })
    elif best_factor and best_factor.get("avg_rating") and best_factor["avg_rating"] >= 4:
        trace.append({
            "step": "Considered lifestyle factors",
            "detail": (f"{best_factor['factor'].replace('_', ' ').title()} nights "
                       f"hit {best_factor['avg_rating']}/5 — good signal"),
        })

    best_hour = insights.get("best_hour")
    if best_hour is not None:
        trace.append({
            "step": "Optimal sleep window",
            "detail": f"Best ratings start around {best_hour:02d}:00",
        })

    if playlist_preview:
        arc = " → ".join(t.get("role", "?") for t in playlist_preview[:3])
        trace.append({
            "step": "Built sleep arc",
            "detail": f"{len(playlist_preview)} tracks · {arc}",
        })

    if chosen_title:
        trace.append({
            "step": "Selected tonight's track",
            "detail": f"'{chosen_title}' — top match for {mood}",
        })

    return trace


def _deterministic_pick(insights: dict, plan: dict, mood: str) -> tuple[str | None, str]:
    """Pick a track and write a fallback reasoning line from MongoDB data alone."""
    best = insights.get("best_track")
    matrix = insights.get("mood_track_matrix", []) or []
    best_hour = insights.get("best_hour")
    streak = insights.get("current_streak", 0)
    mood_hit = next((m for m in matrix if m.get("mood") == mood), None)

    if mood_hit and mood_hit.get("sessions", 0) >= 2:
        title = mood_hit["track"]
        reasoning = (f"{title} leads when you're {mood} — "
                     f"{mood_hit['avg_rating']}/5 across {mood_hit['sessions']} sessions.")
    elif best and best.get("title"):
        title = best["title"]
        reasoning = f"Your top-rated track at {best.get('avg_rating', '?')}/5 — staying with what works."
    else:
        available = plan.get("available_tracks", [])
        title = available[0] if available else None
        reasoning = "Exploring — no clear winner yet, this is a clean start."

    if best_hour is not None:
        reasoning += f" Best window starts around {best_hour:02d}:00."
    if streak >= 2:
        reasoning += f" {streak}-night streak."

    return title, reasoning


def _predict_outcome(insights: dict, mood: str, title: str | None) -> str:
    """Predict tonight's rating from the mood×track cell, or describe the exploration state."""
    if not title:
        return "First night — learning your pattern"
    matrix = insights.get("mood_track_matrix", []) or []
    cell = next((m for m in matrix
                 if m.get("mood") == mood and m.get("track") == title), None)
    if cell and cell.get("sessions", 0) >= 2:
        return f"Predicted {cell['avg_rating']}/5 based on {cell['sessions']} similar nights"
    track_perf = insights.get("track_performance", []) or []
    track_row = next((t for t in track_perf if t.get("title") == title), None)
    if track_row and track_row.get("avg_rating"):
        return f"Track averages {track_row['avg_rating']}/5 — new combination, exploring"
    return "New territory — no prior data for this combo"


def get_recommendation(user_id: str, mood: str = "calm") -> dict:
    """Generate a rich sleep recommendation: deterministic plan + one Gemini call.

    Pre-computes everything from MongoDB (insights, playlist, trace, prediction),
    then issues a single structured-output Gemini call for the creative
    synthesis (vibe caption + reasoning). One LLM call per recommendation.
    """
    _set_user(user_id)

    insights = get_mongodb_sleep_insights()
    plan = recommend_sleep_plan(mood=mood)
    playlist_preview = plan.get("playlist_preview") or []

    title, fallback_reasoning = _deterministic_pick(insights, plan, mood)
    plan_trace = _build_plan_trace(insights, playlist_preview, mood, title)
    predicted_outcome = _predict_outcome(insights, mood, title)

    base = {
        "soundscape_title": title,
        "reasoning": fallback_reasoning,
        "vibe": None,
        "predicted_outcome": predicted_outcome,
        "confidence": 0.6 if title else 0.2,
        "plan_trace": plan_trace,
        "playlist_id": plan.get("playlist_id"),
        "playlist_arc": [
            {"title": t.get("title"), "role": t.get("role")}
            for t in playlist_preview[:3]
        ],
        "source": "deterministic",
    }

    if not _adk_available or not os.environ.get("GOOGLE_API_KEY") or not title:
        return base

    try:
        from google import genai
        from google.genai import types as genai_types
        from pydantic import BaseModel

        class _Synthesis(BaseModel):
            vibe: str
            reasoning: str
            confidence: float

        available_titles = plan.get("available_tracks", [])
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        model = "gemini-3-flash-preview"

        recent_pattern = (insights.get("recent_pattern") or [])[:7]
        recent_notes = (insights.get("recent_notes") or [])[:5]
        context = {
            "user_mood": mood,
            "chosen_track": title,
            "available_tracks": available_titles,
            "playlist_arc": base["playlist_arc"],
            "insights_summary": {
                "best_track": insights.get("best_track"),
                "best_mood": insights.get("best_mood"),
                "best_hour": insights.get("best_hour"),
                "current_streak": insights.get("current_streak"),
                "mood_track_matrix": (insights.get("mood_track_matrix") or [])[:5],
                "best_factor": insights.get("best_factor"),
                "challenging_factor": insights.get("challenging_factor"),
                "note_pattern": insights.get("note_pattern"),
                "stats": insights.get("stats"),
            },
            "recent_nights": [
                {
                    "date": n.get("date"),
                    "rating": n.get("rating"),
                    "energy": n.get("morning_energy"),
                    "track": n.get("track"),
                }
                for n in recent_pattern
            ],
            "recent_notes": recent_notes,
            "trace": plan_trace,
        }

        response = client.models.generate_content(
            model=model,
            contents=(
                "You are sl33p-space, a sleep coach. Produce a synthesis for tonight's plan.\n\n"
                f"CONTEXT (already decided, do not change the track):\n{json.dumps(context, default=str)}\n\n"
                "Return JSON with:\n"
                "- vibe: a 4-8 word poetic caption for tonight's arc (e.g. "
                "'midnight ocean → cathedral hush → deep static'). Evocative, not flowery.\n"
                "- reasoning: ONE sentence (max 24 words) that cites at least one real signal "
                "from the context. Prefer, in order: a recurring note keyword, a recent note, "
                "an energy/rating gap (e.g. 'rating 4 but energy 2'), a track rating, a streak, "
                "or best hour. Reference the journal when notes are present — e.g. "
                "'you mentioned X two nights ago, so...'.\n"
                "- confidence: float 0-1 reflecting data depth. <3 reviewed sessions = ≤0.4."
            ),
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_Synthesis,
                temperature=0.85,
                system_instruction=(
                    "Be specific and concrete. No clichés ('drift off', 'sweet dreams'). "
                    "Cite numbers from the data. Never invent track names."
                ),
            ),
        )

        try:
            from db.usage import log_api_usage
            log_api_usage(user_id=user_id, service="gemini", model=model,
                          cost_usd=0.001, metadata={"purpose": "sleep_recommendation"})
        except Exception:
            pass

        synth = _Synthesis.model_validate_json(response.text)
        base["vibe"] = synth.vibe
        base["reasoning"] = synth.reasoning
        base["confidence"] = max(0.0, min(1.0, synth.confidence))
        base["source"] = "gemini"
        return base
    except Exception:
        return base


# --- Agent setup ---

def _build_prompt(user_id: str) -> str:
    """Build the root prompt with persona context injected."""
    from db.users import get_persona
    persona = get_persona(user_id)
    context = ""
    if persona and persona in PERSONA_CONTEXTS:
        context = PERSONA_CONTEXTS[persona]
    else:
        context = "No specific persona set. Adapt naturally to the user's tone."
    return ROOT_PROMPT.format(persona_context=context)


def create_runner(config: dict = None, prompt: str = None):
    """Create and return an ADK agent runner if google-adk is available."""
    global _root_agent
    if not _adk_available:
        return None
    if not os.environ.get("GOOGLE_API_KEY"):
        return None

    from agent.mcp_loader import load_mcp_tools
    mcp_tools = load_mcp_tools(config or {})
    model = (config or {}).get("agent", {}).get("model", "gemini-flash-latest")

    instruction = prompt or ROOT_PROMPT.format(
        persona_context="No specific persona set. Adapt naturally to the user's tone."
    )

    _root_agent = Agent(
        name="sl33p_space",
        model=model,
        instruction=instruction,
        tools=ROOT_TOOLS + mcp_tools,
    )
    runner = InMemoryRunner(agent=_root_agent, app_name="sl33p-space")
    return runner


def make_chat_handler(config: dict = None):
    """Return a function that handles chat messages via ADK or fallback."""
    if not _adk_available or not os.environ.get("GOOGLE_API_KEY"):
        return _fallback_handler

    import asyncio

    _config = config
    _runners: dict[str, object] = {}
    _sessions: dict[str, str] = {}

    def handle(message: str, user_id: str = "default") -> str:
        _set_user(user_id)

        prompt = _build_prompt(user_id)

        if user_id not in _runners:
            runner = create_runner(_config, prompt=prompt)
            if not runner:
                return _fallback_handler(message, user_id)
            _runners[user_id] = runner

        runner = _runners[user_id]

        async def _run():
            if user_id not in _sessions:
                session = await runner.session_service.create_session(
                    app_name="sl33p-space", user_id=user_id
                )
                _sessions[user_id] = session.id

            content = genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=message)]
            )
            response_parts = []
            async for event in runner.run_async(
                user_id=user_id, session_id=_sessions[user_id],
                new_message=content,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_parts.append(part.text)
            return " ".join(response_parts) if response_parts else "Done."

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_run())
            try:
                from db.usage import log_api_usage
                log_api_usage(user_id=user_id, service="gemini",
                              model=_config.get("agent", {}).get("model", "gemini-flash-latest"),
                              cost_usd=0.002, metadata={"purpose": "chat"})
            except Exception:
                pass
            return result
        finally:
            loop.close()

    return handle


def _fallback_handler(message: str, user_id: str = "default") -> str:
    """Keyword-based handler when ADK is not available — still data-rich."""
    _set_user(user_id)
    msg = message.lower().strip()

    if any(w in msg for w in ["history", "how have i", "how did i"]):
        insights = get_mongodb_sleep_insights()
        if insights.get("available") and insights["stats"].get("reviewed_sessions", 0) > 0:
            best = insights.get("best_track") or {}
            extra = f" Best track: {best.get('title')}." if best.get("title") else ""
            return (f"MongoDB has {insights['stats']['reviewed_sessions']} reviewed sessions "
                    f"with an average rating of {insights['stats'].get('avg_rating') or '?'}/5.{extra}")
        return insights.get("summary") or "No sleep sessions yet. Start your first one!"

    if any(w in msg for w in ["persona", "profile", "who am i"]):
        return ("I can adapt to your sleep style. Choose a persona on the plan page: "
                "Shift Worker, Emergency Services, Shallow Sleeper, or Insomniac.")

    if any(w in msg for w in ["recommend", "opened", "listen", "tonight"]):
        insights = get_mongodb_sleep_insights()
        best = insights.get("best_track") or {}
        if best.get("title"):
            return (f"Tonight I'd start with {best['title']} because MongoDB shows it has "
                    f"your strongest recent rating ({best.get('avg_rating') or '?'} / 5). "
                    "Pick your mood and press Start Sleep to log another session.")
        return insights.get("summary") or "Pick your mood and press Start Sleep to begin learning your pattern."

    if any(w in msg for w in ["sleep", "start", "ready", "tired", "bed"]):
        return ("Ready to sleep? Pick tonight's mood and hit Start Sleep. "
                "The session will be stored in MongoDB so tomorrow's review can improve the next playlist.")

    if any(w in msg for w in ["help", "what can"]):
        return ("I'm your sleep coach. I can summarize MongoDB sleep history, recommend tracks, "
                "start sessions, and learn from tomorrow's review. Add GOOGLE_API_KEY for Gemini reasoning.")

    return ("I can help you sleep better. Try 'history', 'recommend tonight', or 'start sleep'. "
            "Add GOOGLE_API_KEY for full Gemini-powered coaching.")
