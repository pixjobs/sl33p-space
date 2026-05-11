"""
sl33p-space agent built with Google ADK.

When GOOGLE_API_KEY is set, this provides a Gemini-powered sleep assistant.
When not set, it falls back to a simple keyword-based handler so the app
still works without an API key during development.
"""

import json
import os
from typing import Optional

from agent.prompts import ROOT_PROMPT, SLEEP_COACH_PROMPT

_player = None
_library = None
_scheduler = None
_adk_available = False
_root_agent = None

try:
    from google.adk.agents import Agent
    from google.adk.runners import InMemoryRunner
    from google.genai import types as genai_types
    _adk_available = True
except ImportError:
    _adk_available = False


def _load_profiles() -> dict:
    path = os.path.join("data", "profiles.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _save_profiles(profiles: dict):
    os.makedirs("data", exist_ok=True)
    with open(os.path.join("data", "profiles.json"), "w") as f:
        json.dump(profiles, f, indent=2)


# --- Tool functions (plain Python, called by Gemini) ---

def play_sound(sound_type: str, volume: Optional[int] = None,
               duration_minutes: int = 30) -> dict:
    """Play a sleep sound on the bedroom speaker.

    Args:
        sound_type: Type of sound (brown_noise, pink_noise, white_noise, rain,
                    ocean_waves, binaural_beats, ambient_atmosphere, lullaby_drone)
        volume: Volume percentage (0-80). If not specified, uses default.
        duration_minutes: How long to generate the sound file (default 30).

    Returns:
        Status of playback.
    """
    filepath = _library.get_sound(sound_type, duration_minutes)
    if not filepath:
        return {"error": f"Unknown sound type: {sound_type}. Available: {list(_library.get_types().keys())}"}
    return _player.play(filepath, volume=volume)


def stop_playback() -> dict:
    """Stop whatever is currently playing."""
    return _player.stop()


def set_volume(level: int) -> dict:
    """Set the playback volume.

    Args:
        level: Volume percentage (0-80).
    """
    return _player.set_volume(level)


def fade_out(target_volume: int = 0, duration_seconds: int = 900) -> dict:
    """Gradually fade the volume to a target level.

    Args:
        target_volume: Target volume to fade to (default 0 = silence).
        duration_seconds: How long the fade should take in seconds (default 900 = 15 min).
    """
    return _player.fade_to(target_volume, duration_seconds)


def list_sounds() -> dict:
    """List all available sound types and their descriptions."""
    return {"sounds": _library.get_types()}


def generate_sound(sound_type: str, duration_minutes: int = 30,
                   volume: float = 0.5) -> dict:
    """Generate a custom sleep sound file.

    Args:
        sound_type: Type of sound to generate.
        duration_minutes: Duration in minutes.
        volume: Recording volume (0.0 to 1.0).
    """
    return _library.generate_custom(sound_type, duration_minutes, volume)


def generate_music_track(prompt: str, model: str = "lyria-3-clip-preview") -> dict:
    """Generate a unique sleep music track using AI (Lyria). Cached after first generation.

    Args:
        prompt: Description of the music to generate (e.g. "gentle ambient with soft rain textures").
        model: lyria-3-clip-preview for 30-second clips, lyria-3-pro-preview for full songs.

    Returns:
        Path to the generated audio file, or error message.
    """
    from audio.music_gen import generate_music
    return generate_music(prompt, model=model)


def list_music_library() -> dict:
    """List all AI-generated music tracks in the cache."""
    from audio.music_gen import list_generated_music
    return {"tracks": list_generated_music()}


def get_status() -> dict:
    """Get the current playback status including what's playing, volume, etc."""
    state = _player.state
    return {
        "is_playing": state.is_playing,
        "sound": os.path.basename(state.filepath).replace(".wav", "") if state.filepath else "nothing",
        "volume": state.volume,
    }


def create_schedule(profile_name: str, sound_type: str, start_time: str,
                    duration_minutes: int = 30, fade_out_minutes: int = 15,
                    volume: int = 40, recurring: bool = False) -> dict:
    """Create a bedtime schedule that plays automatically.

    Args:
        profile_name: Name of the family member (or 'default').
        sound_type: Type of sound to play.
        start_time: When to start, in HH:MM format (24-hour).
        duration_minutes: How long to play.
        fade_out_minutes: How long to fade out before stopping.
        volume: Playback volume percentage.
        recurring: Whether to repeat every night.
    """
    from audio.scheduler import ScheduledRoutine
    routine = ScheduledRoutine(
        profile_name=profile_name,
        sound_type=sound_type,
        start_time=start_time,
        duration_minutes=duration_minutes,
        fade_out_minutes=fade_out_minutes,
        volume=volume,
        recurring=recurring,
    )
    return _scheduler.schedule(routine)


def cancel_schedule(routine_id: str) -> dict:
    """Cancel a scheduled bedtime routine.

    Args:
        routine_id: The ID of the routine to cancel.
    """
    return _scheduler.cancel(routine_id)


def list_schedules() -> dict:
    """List all active bedtime schedules."""
    return {"schedules": _scheduler.list_routines()}


def get_profile(name: str) -> dict:
    """Get a family member's sleep profile.

    Args:
        name: The family member's name.
    """
    profiles = _load_profiles()
    if name in profiles:
        return profiles[name]
    return {"error": f"No profile found for '{name}'. Available: {list(profiles.keys())}"}


def update_profile(name: str, bedtime: str = None, max_volume: int = None,
                   fade_minutes: int = None, preferred_sounds: list = None) -> dict:
    """Update a family member's sleep preferences.

    Args:
        name: The family member's name.
        bedtime: Preferred bedtime in HH:MM format.
        max_volume: Maximum allowed volume percentage.
        fade_minutes: Default fade-out duration in minutes.
        preferred_sounds: List of preferred sound types.
    """
    profiles = _load_profiles()
    profile = profiles.get(name, {
        "name": name,
        "preferred_sounds": ["brown_noise"],
        "bedtime": "20:00",
        "max_volume": 60,
        "fade_minutes": 15,
    })
    if bedtime is not None:
        profile["bedtime"] = bedtime
    if max_volume is not None:
        profile["max_volume"] = min(max_volume, _player.max_volume)
    if fade_minutes is not None:
        profile["fade_minutes"] = fade_minutes
    if preferred_sounds is not None:
        profile["preferred_sounds"] = preferred_sounds
    profiles[name] = profile
    _save_profiles(profiles)
    return {"updated": name, "profile": profile}


SLEEP_COACH_TOOLS = [
    get_profile, update_profile, play_sound, fade_out, get_status,
    create_schedule, cancel_schedule, list_schedules,
    generate_music_track, list_music_library,
]

ROOT_TOOLS = [
    play_sound, stop_playback, set_volume, fade_out,
    list_sounds, generate_sound, get_status,
    update_profile,
    generate_music_track, list_music_library,
]

ALL_TOOLS = ROOT_TOOLS + [
    create_schedule, cancel_schedule, list_schedules,
    get_profile,
]


def init(player, library, scheduler):
    global _player, _library, _scheduler
    _player = player
    _library = library
    _scheduler = scheduler


def create_runner(config: dict = None):
    """Create and return an ADK agent runner if google-adk is available."""
    global _root_agent
    if not _adk_available:
        return None
    if not os.environ.get("GOOGLE_API_KEY"):
        return None

    from agent.mcp_loader import load_mcp_tools
    mcp_tools = load_mcp_tools(config or {})
    model = (config or {}).get("agent", {}).get("model", "gemini-flash-latest")

    sleep_coach = Agent(
        name="sleep_coach",
        model=model,
        description="Handles bedtime setup: profile lookup, history-based recommendation, "
                    "playback, fade-out scheduling, and routine creation.",
        instruction=SLEEP_COACH_PROMPT,
        tools=SLEEP_COACH_TOOLS + mcp_tools,
        disallow_transfer_to_parent=False,
    )

    _root_agent = Agent(
        name="sl33p_space",
        model=model,
        instruction=ROOT_PROMPT,
        tools=ROOT_TOOLS,
        sub_agents=[sleep_coach],
    )
    runner = InMemoryRunner(agent=_root_agent, app_name="sl33p-space")
    return runner


def make_chat_handler(config: dict = None):
    """Return a function that handles chat messages via ADK or fallback."""
    runner = create_runner(config)

    if runner:
        import asyncio
        from google.genai import types as genai_types

        session_id = None

        def handle(message: str) -> str:
            nonlocal session_id

            async def _run():
                nonlocal session_id
                if session_id is None:
                    session = await runner.session_service.create_session(
                        app_name="sl33p-space", user_id="parent"
                    )
                    session_id = session.id

                content = genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=message)]
                )
                response_parts = []
                async for event in runner.run_async(
                    user_id="parent", session_id=session_id, new_message=content
                ):
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                response_parts.append(part.text)
                return " ".join(response_parts) if response_parts else "Done."

            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_run())
            finally:
                loop.close()

        return handle

    return _fallback_handler


def _fallback_handler(message: str) -> str:
    """Simple keyword-based handler when ADK is not available."""
    msg = message.lower().strip()

    if any(w in msg for w in ["play", "start"]):
        for sound_type in _library.get_types():
            if sound_type.replace("_", " ") in msg or sound_type in msg:
                result = play_sound(sound_type)
                return f"Playing {sound_type.replace('_', ' ')}. {json.dumps(result)}"
        result = play_sound("brown_noise")
        return f"Playing brown noise (default). Set GOOGLE_API_KEY for smarter responses."

    if any(w in msg for w in ["stop", "quiet", "silence"]):
        stop_playback()
        return "Stopped playback."

    if "fade" in msg:
        fade_out()
        return "Fading out over 15 minutes."

    if any(w in msg for w in ["volume", "louder", "softer"]):
        return f"Current volume: {get_status()['volume']}%. Use the volume slider to adjust."

    if any(w in msg for w in ["sound", "list", "available", "type"]):
        types = list_sounds()["sounds"]
        return "Available sounds: " + ", ".join(k.replace("_", " ") for k in types)

    if any(w in msg for w in ["status", "what", "playing"]):
        s = get_status()
        if s["is_playing"]:
            return f"Currently playing: {s['sound']} at {s['volume']}% volume."
        return "Nothing is playing right now."

    if any(w in msg for w in ["help", "what can"]):
        return ("I can play sleep sounds, set schedules, and manage family profiles. "
                "Try: 'play rain', 'list sounds', 'stop', or 'fade out'. "
                "Set GOOGLE_API_KEY for full natural language support.")

    return ("I'm not sure what you mean. Try 'play brown noise', 'stop', 'fade out', "
            "or 'list sounds'. Set GOOGLE_API_KEY for full Gemini-powered responses.")
