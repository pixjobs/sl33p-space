import json
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from web.auth import init_auth, require_auth, get_user_id, get_current_user, is_dev_mode

_player = None
_library = None
_scheduler = None
_agent_runner = None


def _load_config() -> dict:
    try:
        with open("config/config.json") as f:
            return json.load(f)
    except Exception:
        return {}


def create_app(player, library, scheduler, agent_runner=None):
    global _player, _library, _scheduler, _agent_runner
    _player = player
    _library = library
    _scheduler = scheduler
    _agent_runner = agent_runner

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    init_auth(app)

    @app.context_processor
    def _inject_firebase_config():
        if is_dev_mode():
            return {"firebase_config": None}
        cfg = {
            "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
            "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
            "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
            "appId": os.environ.get("FIREBASE_APP_ID", ""),
        }
        if not cfg["apiKey"]:
            return {"firebase_config": None}
        return {"firebase_config": cfg}

    @app.route("/healthz")
    def healthz():
        return "ok", 200

    @app.route("/")
    def index():
        user = get_current_user()
        if user:
            return redirect(url_for("plan"))
        return render_template("welcome.html")

    @app.route("/plan")
    @require_auth
    def plan():
        from audio.music_gen import list_generated_music, get_preset_prompts
        from db.sessions import get_pending_review, get_recent_sessions, get_sleep_stats

        user = get_current_user()
        uid = get_user_id()
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        return render_template(
            "plan.html",
            greeting=greeting,
            user_name=user.get("name", "").split()[0] if user.get("name") else "there",
            stats=get_sleep_stats(uid),
            pending_review=get_pending_review(uid),
            recent_sessions=get_recent_sessions(uid, limit=5),
            tracks=list_generated_music(),
            presets=get_preset_prompts(),
            has_agent=bool(os.environ.get("GOOGLE_API_KEY")),
        )

    @app.route("/media/music/<path:filename>")
    def serve_music(filename):
        music_dir = os.path.abspath("data/music")
        return send_from_directory(music_dir, filename)

    @app.route("/api/status")
    def api_status():
        state = _player.state
        return jsonify({
            "is_playing": state.is_playing,
            "filepath": state.filepath,
            "volume": state.volume,
            "sound_name": os.path.splitext(os.path.basename(state.filepath))[0] if state.filepath else "",
        })

    @app.route("/api/sounds")
    def api_sounds():
        return jsonify(_library.list_sounds())

    @app.route("/api/play", methods=["POST"])
    @require_auth
    def api_play():
        data = request.get_json(force=True)
        sound_type = data.get("sound_type", "brown_noise")
        duration = data.get("duration_minutes", 30)
        volume = data.get("volume")
        filepath = _library.get_sound(sound_type, duration)
        if not filepath:
            return jsonify({"error": f"Unknown sound type: {sound_type}"}), 400
        result = _player.play(filepath, volume=volume)
        return jsonify(result)

    @app.route("/api/stop", methods=["POST"])
    @require_auth
    def api_stop():
        return jsonify(_player.stop())

    @app.route("/api/volume", methods=["POST"])
    @require_auth
    def api_volume():
        data = request.get_json(force=True)
        level = data.get("volume", 40)
        return jsonify(_player.set_volume(int(level)))

    @app.route("/api/fade", methods=["POST"])
    @require_auth
    def api_fade():
        data = request.get_json(force=True)
        target = data.get("target", 0)
        seconds = data.get("seconds", 900)
        return jsonify(_player.fade_to(int(target), int(seconds)))

    @app.route("/api/chat", methods=["POST"])
    @require_auth
    def api_chat():
        data = request.get_json(force=True)
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "Empty message"}), 400
        if _agent_runner:
            response = _agent_runner(message, get_user_id())
            return jsonify({"response": response})
        return jsonify({"response": "Agent not configured. Set GOOGLE_API_KEY to enable."})

    @app.route("/api/profiles", methods=["GET"])
    def api_profiles():
        return jsonify(_load_profiles())

    @app.route("/api/profiles", methods=["POST"])
    @require_auth
    def api_profiles_update():
        data = request.get_json(force=True)
        profiles = _load_profiles()
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        profiles[name] = {
            "name": name,
            "preferred_sounds": data.get("preferred_sounds", ["brown_noise"]),
            "bedtime": data.get("bedtime", "20:00"),
            "max_volume": min(data.get("max_volume", 60), _player.max_volume),
            "fade_minutes": data.get("fade_minutes", 15),
        }
        _save_profiles(profiles)
        return jsonify({"saved": name})

    @app.route("/api/profiles/<name>", methods=["DELETE"])
    @require_auth
    def api_profiles_delete(name):
        profiles = _load_profiles()
        if name in profiles:
            del profiles[name]
            _save_profiles(profiles)
            return jsonify({"deleted": name})
        return jsonify({"error": "Not found"}), 404

    @app.route("/api/schedules", methods=["POST"])
    @require_auth
    def api_schedules_create():
        from audio.scheduler import ScheduledRoutine
        data = request.get_json(force=True)
        routine = ScheduledRoutine(
            profile_name=data.get("profile_name", "default"),
            sound_type=data.get("sound_type", "brown_noise"),
            start_time=data.get("start_time", "20:00"),
            duration_minutes=data.get("duration_minutes", 30),
            fade_out_minutes=data.get("fade_out_minutes", 15),
            volume=data.get("volume", 40),
            recurring=data.get("recurring", False),
        )
        return jsonify(_scheduler.schedule(routine))

    @app.route("/api/schedules/<routine_id>", methods=["DELETE"])
    @require_auth
    def api_schedules_delete(routine_id):
        return jsonify(_scheduler.cancel(routine_id))

    @app.route("/api/music/generate", methods=["POST"])
    @require_auth
    def api_music_generate():
        from audio.music_gen import generate_music
        data = request.get_json(force=True)
        prompt = data.get("prompt", "ambient sleep music")
        title = data.get("title", "")
        return jsonify(generate_music(prompt, title=title, user_id=get_user_id()))

    @app.route("/api/music/library")
    def api_music_library():
        from audio.music_gen import list_generated_music
        return jsonify(list_generated_music())

    @app.route("/api/music/<track_id>", methods=["DELETE"])
    @require_auth
    def api_music_delete(track_id):
        from audio.music_gen import delete_track
        result = delete_track(track_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/music/<track_id>/archive", methods=["POST"])
    @require_auth
    def api_music_archive(track_id):
        from audio.music_gen import archive_track
        result = archive_track(track_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/music/<track_id>/unarchive", methods=["POST"])
    @require_auth
    def api_music_unarchive(track_id):
        from audio.music_gen import unarchive_track
        result = unarchive_track(track_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/music/archive")
    def api_music_archive_list():
        from audio.music_gen import list_archived_music
        return jsonify(list_archived_music())

    @app.route("/api/music/suggest")
    def api_music_suggest():
        from audio.music_gen import suggest_prompts, list_generated_music
        existing = [t["title"] for t in list_generated_music()]
        return jsonify(suggest_prompts(existing))

    @app.route("/api/music/suggest-variation", methods=["POST"])
    def api_music_suggest_variation():
        from audio.music_gen import suggest_variation
        data = request.get_json(force=True)
        prompt = data.get("prompt", "")
        if not prompt:
            return jsonify({"error": "prompt required"}), 400
        return jsonify(suggest_variation(prompt))

    # ───── Sleep Session Routes ─────

    @app.route("/sleep")
    @require_auth
    def sleep_view():
        session_id = request.args.get("session", "")
        track_src = request.args.get("track", "")
        track_title = request.args.get("title", "")
        return render_template(
            "sleep.html",
            session_id=session_id,
            track_src=track_src,
            track_title=track_title,
        )

    @app.route("/review")
    @require_auth
    def review_view():
        from db.sessions import get_pending_review
        uid = get_user_id()
        pending = get_pending_review(uid)
        if not pending:
            return redirect(url_for("plan"))
        return render_template("review.html", session=pending)

    @app.route("/api/sleep/recommend", methods=["POST"])
    @require_auth
    def api_sleep_recommend():
        data = request.get_json(force=True)
        mood = data.get("mood", "calm")
        uid = get_user_id()

        from db.sessions import get_recent_sessions, get_sleep_stats
        from audio.music_gen import list_generated_music
        recent = get_recent_sessions(uid, limit=5)
        stats = get_sleep_stats(uid)
        tracks = list_generated_music()

        if _agent_runner and os.environ.get("GOOGLE_API_KEY"):
            try:
                from google import genai
                client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
                history_text = ""
                for s in recent[:5]:
                    r = s.get("review") or {}
                    history_text += f"- {s['plan'].get('soundscape_title','?')}: {r.get('rating','?')}/5, {s['actual'].get('duration_minutes',0):.0f}min\n"
                track_list = ", ".join(t["title"] for t in tracks[:10])
                prompt = (
                    f"User mood: {mood}\n"
                    f"Recent sleep sessions:\n{history_text or 'None yet'}\n"
                    f"Stats: {stats}\n"
                    f"Available tracks: {track_list or 'None'}\n\n"
                    "Recommend a sleep plan. Respond with ONLY valid JSON, no markdown:\n"
                    '{"soundscape_title": "...", "duration_hours": 7.5, '
                    '"wind_down": "...", "reasoning": "one sentence"}'
                )
                response = client.models.generate_content(
                    model=_load_config().get("agent", {}).get("model", "gemini-flash-latest"),
                    contents=prompt,
                    config={"system_instruction": "You are a sleep coach. Be concise.", "temperature": 0.7},
                )
                text = response.text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                rec = json.loads(text)
                return jsonify(rec)
            except Exception:
                pass

        default_sound = stats.get("top_sound") or (tracks[0]["title"] if tracks else "Brown Noise")
        return jsonify({
            "soundscape_title": default_sound,
            "duration_hours": 7.5,
            "wind_down": "4-7-8 breathing for 5 minutes",
            "reasoning": "Based on your preferences" if stats.get("total_sessions") else "A good starting point for restful sleep",
        })

    @app.route("/api/sleep/plan", methods=["POST"])
    @require_auth
    def api_sleep_plan():
        from db.sessions import create_session
        data = request.get_json(force=True)
        uid = get_user_id()
        plan = {
            "soundscape_id": data.get("soundscape_id"),
            "soundscape_title": data.get("soundscape_title"),
            "soundscape_src": data.get("soundscape_src"),
            "duration_target_hours": data.get("duration_hours", 7.5),
            "wind_down": data.get("wind_down", ""),
            "mood": data.get("mood", "calm"),
        }
        session_id = create_session(uid, plan)
        if session_id:
            return jsonify({"session_id": session_id})
        return jsonify({"session_id": None, "status": "ok"})

    @app.route("/api/sleep/start", methods=["POST"])
    @require_auth
    def api_sleep_start():
        from db.sessions import start_session
        data = request.get_json(force=True)
        sid = data.get("session_id")
        track = data.get("track")
        if sid:
            start_session(sid, track=track)
        return jsonify({"status": "ok"})

    @app.route("/api/sleep/end", methods=["POST"])
    @require_auth
    def api_sleep_end():
        from db.sessions import end_session, get_active_session
        data = request.get_json(force=True)
        sid = data.get("session_id")
        if not sid:
            session = get_active_session(get_user_id())
            sid = session["_id"] if session else None
        if sid:
            end_session(sid)
        return jsonify({"status": "ok"})

    @app.route("/api/sleep/review", methods=["POST"])
    @require_auth
    def api_sleep_review():
        from db.sessions import review_session, skip_review
        data = request.get_json(force=True)
        sid = data.get("session_id")
        if not sid:
            return jsonify({"error": "session_id required"}), 400
        if data.get("skip"):
            skip_review(sid)
        else:
            rating = int(data.get("rating", 3))
            notes = data.get("notes", "")
            review_session(sid, rating, notes)
        return jsonify({"status": "ok"})

    @app.route("/api/sleep/current")
    @require_auth
    def api_sleep_current():
        from db.sessions import get_active_session
        session = get_active_session(get_user_id())
        return jsonify(session or {})

    @app.route("/api/sleep/history")
    @require_auth
    def api_sleep_history():
        from db.sessions import get_recent_sessions, get_sleep_stats
        uid = get_user_id()
        return jsonify({
            "sessions": get_recent_sessions(uid),
            "stats": get_sleep_stats(uid),
        })

    # ───── Scene Routes ─────

    @app.route("/api/scenes/cosmos")
    def api_scenes_cosmos():
        from web.scenes import get_apod
        result = get_apod()
        if result:
            return jsonify(result)
        return jsonify({"error": "No APOD available"}), 404

    @app.route("/api/scenes/scenic")
    def api_scenes_scenic():
        from db.assets import get_random_scene
        theme = request.args.get("theme", "beach")
        scene = get_random_scene(theme)
        if scene:
            return jsonify({
                "url": "/api/scenes/image/" + os.path.basename(scene.get("storage_path", "")),
                "theme": scene.get("theme"),
                "title": scene.get("title", ""),
            })
        return jsonify({"error": "No scenes available"}), 404

    @app.route("/api/scenes/image/<path:filename>")
    def serve_scene_image(filename):
        scenes_dir = os.path.abspath("data/scenes")
        for theme_dir in os.listdir(scenes_dir) if os.path.isdir(scenes_dir) else []:
            full_path = os.path.join(scenes_dir, theme_dir, filename)
            if os.path.exists(full_path):
                return send_from_directory(os.path.join(scenes_dir, theme_dir), filename)
        return "Not found", 404

    @app.route("/api/user/preferences", methods=["GET"])
    @require_auth
    def api_user_prefs_get():
        from db.users import get_user
        user = get_user(get_user_id())
        if user:
            return jsonify(user.get("preferences", {}))
        return jsonify({})

    @app.route("/api/user/preferences", methods=["POST"])
    @require_auth
    def api_user_prefs_update():
        from db.users import update_preferences
        data = request.get_json(force=True)
        update_preferences(get_user_id(), data)
        return jsonify({"status": "ok"})

    return app


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
