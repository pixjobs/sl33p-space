import json
import os
from flask import Flask, render_template, request, jsonify, send_from_directory

_player = None
_library = None
_scheduler = None
_agent_runner = None


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

    @app.route("/")
    def index():
        from audio.music_gen import list_generated_music, list_archived_music, get_preset_prompts
        state = _player.state
        return render_template(
            "index.html",
            state=state,
            presets=get_preset_prompts(),
            tracks=list_generated_music(),
            archived_tracks=list_archived_music(),
            sound_types=_library.get_types(),
            has_agent=bool(os.environ.get("GOOGLE_API_KEY")),
        )

    @app.route("/settings")
    def settings():
        return render_template(
            "settings.html",
            profiles=_load_profiles(),
            routines=_scheduler.list_routines(),
            sound_types=_library.get_types(),
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
            "sound_name": os.path.basename(state.filepath).replace(".wav", "") if state.filepath else "",
        })

    @app.route("/api/sounds")
    def api_sounds():
        return jsonify(_library.list_sounds())

    @app.route("/api/play", methods=["POST"])
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
    def api_stop():
        return jsonify(_player.stop())

    @app.route("/api/volume", methods=["POST"])
    def api_volume():
        data = request.get_json(force=True)
        level = data.get("volume", 40)
        return jsonify(_player.set_volume(int(level)))

    @app.route("/api/fade", methods=["POST"])
    def api_fade():
        data = request.get_json(force=True)
        target = data.get("target", 0)
        seconds = data.get("seconds", 900)
        return jsonify(_player.fade_to(int(target), int(seconds)))

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        data = request.get_json(force=True)
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "Empty message"}), 400
        if _agent_runner:
            response = _agent_runner(message)
            return jsonify({"response": response})
        return jsonify({"response": "Agent not configured. Set GOOGLE_API_KEY to enable."})

    @app.route("/api/profiles", methods=["GET"])
    def api_profiles():
        return jsonify(_load_profiles())

    @app.route("/api/profiles", methods=["POST"])
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
    def api_profiles_delete(name):
        profiles = _load_profiles()
        if name in profiles:
            del profiles[name]
            _save_profiles(profiles)
            return jsonify({"deleted": name})
        return jsonify({"error": "Not found"}), 404

    @app.route("/api/schedules", methods=["POST"])
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
    def api_schedules_delete(routine_id):
        return jsonify(_scheduler.cancel(routine_id))

    @app.route("/api/music/generate", methods=["POST"])
    def api_music_generate():
        from audio.music_gen import generate_music
        data = request.get_json(force=True)
        prompt = data.get("prompt", "ambient sleep music")
        title = data.get("title", "")
        model = data.get("model", "lyria-3-clip-preview")
        return jsonify(generate_music(prompt, title=title, model=model))

    @app.route("/api/music/library")
    def api_music_library():
        from audio.music_gen import list_generated_music
        return jsonify(list_generated_music())

    @app.route("/api/music/<track_id>", methods=["DELETE"])
    def api_music_delete(track_id):
        from audio.music_gen import delete_track
        result = delete_track(track_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/music/<track_id>/archive", methods=["POST"])
    def api_music_archive(track_id):
        from audio.music_gen import archive_track
        result = archive_track(track_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/music/<track_id>/unarchive", methods=["POST"])
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
