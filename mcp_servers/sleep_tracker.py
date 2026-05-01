#!/usr/bin/env python3
"""
Sleep Tracker MCP Server

A local MCP server providing sleep session logging and analytics.
Runs over stdio transport -- launched by the ADK agent via config.

Tools:
  - log_sleep_session: Record a completed sleep session
  - get_sleep_history: Query recent sessions for a profile
  - get_sleep_stats: Aggregated sleep statistics
  - get_sleep_recommendation: Data-driven sound/time suggestions
"""

import json
import os
import sys
from datetime import datetime, timedelta

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "sleep_log.json")

server = Server("sleep-tracker")


def _load_log() -> list[dict]:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return []


def _save_log(entries: list[dict]):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(entries, f, indent=2)


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="log_sleep_session",
            description="Record a completed sleep session for a family member.",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {"type": "string", "description": "Family member name"},
                    "sound_type": {"type": "string", "description": "Sound that was played"},
                    "duration_minutes": {"type": "number", "description": "How long the session lasted"},
                    "completed": {"type": "boolean", "description": "Whether the full duration played", "default": True},
                    "notes": {"type": "string", "description": "Optional notes (e.g. 'fell asleep quickly')", "default": ""},
                },
                "required": ["profile", "sound_type", "duration_minutes"],
            },
        ),
        Tool(
            name="get_sleep_history",
            description="Get recent sleep sessions for a family member.",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {"type": "string", "description": "Family member name"},
                    "days": {"type": "number", "description": "How many days back to look", "default": 7},
                },
                "required": ["profile"],
            },
        ),
        Tool(
            name="get_sleep_stats",
            description="Get aggregated sleep statistics for a family member.",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {"type": "string", "description": "Family member name"},
                },
                "required": ["profile"],
            },
        ),
        Tool(
            name="get_sleep_recommendation",
            description="Get a data-driven sleep recommendation based on past sessions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {"type": "string", "description": "Family member name"},
                },
                "required": ["profile"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "log_sleep_session":
        return await _log_session(arguments)
    elif name == "get_sleep_history":
        return await _get_history(arguments)
    elif name == "get_sleep_stats":
        return await _get_stats(arguments)
    elif name == "get_sleep_recommendation":
        return await _get_recommendation(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _log_session(args: dict):
    entries = _load_log()
    entry = {
        "profile": args["profile"],
        "sound_type": args["sound_type"],
        "duration_minutes": args["duration_minutes"],
        "completed": args.get("completed", True),
        "notes": args.get("notes", ""),
        "timestamp": datetime.now().isoformat(),
    }
    entries.append(entry)
    _save_log(entries)
    return [TextContent(
        type="text",
        text=f"Logged: {entry['profile']} slept {entry['duration_minutes']}min with {entry['sound_type']}"
    )]


async def _get_history(args: dict):
    entries = _load_log()
    profile = args["profile"].lower()
    days = args.get("days", 7)
    cutoff = datetime.now() - timedelta(days=days)

    matches = [
        e for e in entries
        if e["profile"].lower() == profile
        and datetime.fromisoformat(e["timestamp"]) > cutoff
    ]

    if not matches:
        return [TextContent(type="text", text=f"No sleep sessions found for {args['profile']} in the last {days} days.")]

    lines = [f"Sleep history for {args['profile']} (last {days} days):"]
    for e in sorted(matches, key=lambda x: x["timestamp"], reverse=True):
        ts = datetime.fromisoformat(e["timestamp"]).strftime("%a %H:%M")
        status = "completed" if e.get("completed", True) else "interrupted"
        lines.append(f"  {ts} - {e['sound_type']} for {e['duration_minutes']}min ({status})")
        if e.get("notes"):
            lines.append(f"    Note: {e['notes']}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _get_stats(args: dict):
    entries = _load_log()
    profile = args["profile"].lower()
    matches = [e for e in entries if e["profile"].lower() == profile]

    if not matches:
        return [TextContent(type="text", text=f"No data for {args['profile']} yet.")]

    total_sessions = len(matches)
    total_minutes = sum(e["duration_minutes"] for e in matches)
    avg_duration = total_minutes / total_sessions
    completed = sum(1 for e in matches if e.get("completed", True))
    completion_rate = completed / total_sessions * 100

    sound_counts: dict[str, int] = {}
    for e in matches:
        sound_counts[e["sound_type"]] = sound_counts.get(e["sound_type"], 0) + 1
    favorite = max(sound_counts, key=sound_counts.get)

    last_7 = [
        e for e in matches
        if datetime.fromisoformat(e["timestamp"]) > datetime.now() - timedelta(days=7)
    ]

    return [TextContent(type="text", text=(
        f"Sleep stats for {args['profile']}:\n"
        f"  Total sessions: {total_sessions}\n"
        f"  Average duration: {avg_duration:.0f} minutes\n"
        f"  Completion rate: {completion_rate:.0f}%\n"
        f"  Favorite sound: {favorite} ({sound_counts[favorite]} sessions)\n"
        f"  Sessions this week: {len(last_7)}\n"
        f"  All sounds used: {', '.join(sorted(sound_counts.keys()))}"
    ))]


async def _get_recommendation(args: dict):
    entries = _load_log()
    profile = args["profile"].lower()
    matches = [e for e in entries if e["profile"].lower() == profile]

    if len(matches) < 3:
        return [TextContent(type="text", text=(
            f"Not enough data for {args['profile']} yet (need at least 3 sessions). "
            "Try brown noise or rain sounds for 30 minutes as a starting point."
        ))]

    completed = [e for e in matches if e.get("completed", True)]
    interrupted = [e for e in matches if not e.get("completed", True)]

    best_sounds: dict[str, float] = {}
    for e in completed:
        s = e["sound_type"]
        best_sounds[s] = best_sounds.get(s, 0) + 1
    for e in interrupted:
        s = e["sound_type"]
        best_sounds[s] = best_sounds.get(s, 0) - 0.5

    if best_sounds:
        recommended_sound = max(best_sounds, key=best_sounds.get)
    else:
        recommended_sound = "brown_noise"

    avg_dur = sum(e["duration_minutes"] for e in completed) / max(len(completed), 1)
    recommended_dur = round(avg_dur / 5) * 5  # round to nearest 5

    recent = sorted(matches, key=lambda x: x["timestamp"], reverse=True)[:5]
    recent_times = []
    for e in recent:
        try:
            t = datetime.fromisoformat(e["timestamp"])
            recent_times.append(t.hour * 60 + t.minute)
        except (ValueError, KeyError):
            pass

    if recent_times:
        avg_time_min = sum(recent_times) // len(recent_times)
        rec_hour, rec_min = divmod(avg_time_min, 60)
        rec_time = f"{rec_hour:02d}:{rec_min:02d}"
    else:
        rec_time = "20:00"

    return [TextContent(type="text", text=(
        f"Recommendation for {args['profile']}:\n"
        f"  Sound: {recommended_sound} (best completion rate)\n"
        f"  Duration: {recommended_dur} minutes\n"
        f"  Start time: {rec_time} (based on recent patterns)\n"
        f"  Based on {len(matches)} sessions ({len(completed)} completed, {len(interrupted)} interrupted)"
    ))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
