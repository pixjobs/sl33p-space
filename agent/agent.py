"""
sl33p-space agent built with Google ADK.

When GOOGLE_API_KEY is set, this provides a Gemini-powered sleep assistant.
When not set, it falls back to a simple keyword-based handler so the app
still works without an API key during development.
"""

import json
import os
from typing import Optional

from agent.prompts import ROOT_PROMPT, PERSONA_CONTEXTS

_adk_available = False
_root_agent = None
_current_user_id = "default"

try:
    from google.adk.agents import Agent
    from google.adk.runners import InMemoryRunner
    from google.genai import types as genai_types
    _adk_available = True
except ImportError:
    _adk_available = False


VALID_PERSONAS = ["shift_worker", "emergency_services", "shallow_sleeper", "insomniac"]
VALID_FACTORS = ["caffeine", "exercise", "screen_time", "stress", "alcohol", "nap", "late_meal"]


# --- Tool functions (called by Gemini) ---

def generate_music_track(prompt: str) -> dict:
    """Generate a unique sleep music track using AI (Lyria).

    Args:
        prompt: Description of the music to generate (e.g. "gentle ambient with soft rain textures").

    Returns:
        Path to the generated audio file, or error message.
    """
    from audio.music_gen import generate_music
    return generate_music(prompt, user_id=_current_user_id)


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
    sessions = get_recent_sessions(_current_user_id, limit=limit)
    stats = get_sleep_stats(_current_user_id)
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
    return get_user_sleep_insights(_current_user_id, days=days)


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

    tracks = list_generated_music()
    stats = get_sleep_stats(_current_user_id)
    persona = get_persona(_current_user_id)
    insights = get_mongodb_sleep_insights()
    if mood == "calm" and insights.get("recommended_mood"):
        mood = insights["recommended_mood"]

    playlist_data = build_playlist(mood, persona, _current_user_id)
    playlist_tracks = []
    if playlist_data:
        playlist_tracks = [
            {"title": t["title"], "role": t["role"], "energy": t.get("energy_level")}
            for t in playlist_data.get("tracks", [])
        ]

    best_rated = None
    for s in get_recent_sessions(_current_user_id, limit=7):
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

    tracks = list_generated_music()
    persona = get_persona(_current_user_id)

    playlist_data = build_playlist(mood, persona, _current_user_id)
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

    session_id = create_session(_current_user_id, plan, playlist_id=playlist_id)
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
    persona = get_persona(_current_user_id)
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
    set_persona(_current_user_id, persona_key or None)
    return {"set": persona_key or None}


def get_tracking_level() -> dict:
    """Get the user's data tracking preference (minimal, basic, or detailed)."""
    from db.users import get_user
    user = get_user(_current_user_id)
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
    return get_user_tier(_current_user_id)


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
    return get_user_feedback_summary(_current_user_id, limit=limit)


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
        _current_user_id = user_id

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
    """Simple keyword-based handler when ADK is not available."""
    global _current_user_id
    msg = message.lower().strip()

    if any(w in msg for w in ["history", "how have i", "how did i"]):
        _current_user_id = user_id
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
        _current_user_id = user_id
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
