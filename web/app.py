import json
import os
from flask import Flask, render_template, request, jsonify

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
        sounds = _library.list_sounds()
        routines = _scheduler.list_routines()
        state = _player.state
        profiles = _load_profiles()
        return render_template(
            "index.html",
            sounds=sounds,
            routines=routines,
            state=state,
            profiles=profiles,
            sound_types=_library.get_types(),
        )

    @app.route("/kid/<name>")
    def kid_view(name):
        profiles = _load_profiles()
        if name not in profiles:
            return f"No profile for '{name}'. Create one at <a href='/profiles'>/profiles</a>.", 404
        profile = profiles[name]
        sounds = profile.get("preferred_sounds", list(_library.get_types().keys()))
        return render_template("kid.html", profile=profile, sounds=sounds)

    @app.route("/chat")
    def chat():
        return render_template("chat.html")

    @app.route("/profiles")
    def profiles():
        return render_template("profiles.html", profiles=_load_profiles())

    @app.route("/schedules")
    def schedules():
        return render_template(
            "schedules.html",
            routines=_scheduler.list_routines(),
            profiles=_load_profiles(),
            sound_types=_library.get_types(),
        )

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
        model = data.get("model", "lyria-3-clip-preview")
        return jsonify(generate_music(prompt, model=model))

    @app.route("/api/music/nasa", methods=["POST"])
    def api_music_nasa():
        from audio.music_gen import generate_from_nasa_apod
        data = request.get_json(force=True)
        date = data.get("date")
        return jsonify(generate_from_nasa_apod(date))

    @app.route("/api/music/library")
    def api_music_library():
        from audio.music_gen import list_generated_music
        return jsonify(list_generated_music())

    @app.route("/api/music/play", methods=["POST"])
    def api_music_play():
        data = request.get_json(force=True)
        path = data.get("path", "")
        volume = data.get("volume")
        if not path or not os.path.exists(path):
            return jsonify({"error": "Track not found"}), 404
        return jsonify(_player.play(path, volume=volume))

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
