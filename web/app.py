import json
import os
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from web.auth import init_auth, require_auth, require_login, get_user_id, get_current_user, is_dev_mode

_agent_runner = None
_seeding = False


def _load_config() -> dict:
    try:
        with open("config/config.json") as f:
            return json.load(f)
    except Exception:
        return {}


def create_app(agent_runner=None):
    global _agent_runner
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
        from db.insights import get_user_sleep_insights
        from db.users import get_user

        user = get_current_user()
        uid = get_user_id()
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        tracks = list_generated_music()

        global _seeding
        if len(tracks) < 5 and not _seeding and os.environ.get("GOOGLE_API_KEY"):
            _seeding = True
            def _seed_bg():
                global _seeding
                try:
                    from audio.music_gen import seed_n_tracks
                    seed_n_tracks(5 - len(tracks))
                finally:
                    _seeding = False
            threading.Thread(target=_seed_bg, daemon=True).start()

        db_user = get_user(uid)
        prefs = (db_user or {}).get("preferences", {})
        persona = prefs.get("persona")
        tracking_level = prefs.get("tracking_level", "basic")

        from db.tiers import get_user_tier
        user_tier = get_user_tier(uid)
        insights = get_user_sleep_insights(uid)

        return render_template(
            "plan.html",
            greeting=greeting,
            user_name=user.get("name", "").split()[0] if user.get("name") else "there",
            stats=get_sleep_stats(uid),
            pending_review=get_pending_review(uid),
            recent_sessions=get_recent_sessions(uid, limit=5),
            tracks=tracks,
            presets=get_preset_prompts(),
            has_agent=bool(os.environ.get("GOOGLE_API_KEY")),
            seeding=_seeding,
            persona=persona,
            tracking_level=tracking_level,
            user_tier=user_tier,
            insights=insights,
        )

    @app.route("/media/music/<path:filename>")
    def serve_music(filename):
        music_dir = os.path.abspath("data/music")
        return send_from_directory(music_dir, filename)

    # ───── Chat ─────

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

    # ───── Music Routes ─────

    @app.route("/api/music/generate", methods=["POST"])
    @require_login
    def api_music_generate():
        from audio.music_gen import generate_music
        from db.tiers import check_generation_allowance, consume_generation
        uid = get_user_id()

        allowed, reason = check_generation_allowance(uid)
        if not allowed:
            return jsonify({"error": reason}), 403

        data = request.get_json(force=True)
        prompt = data.get("prompt", "ambient sleep music")
        title = data.get("title", "")
        result = generate_music(prompt, title=title, user_id=uid)

        if "error" not in result and not result.get("cached"):
            consume_generation(uid)

        return jsonify(result)

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

    @app.route("/api/music/seed", methods=["POST"])
    @require_auth
    def api_music_seed():
        from audio.music_gen import seed_library
        result = seed_library()
        return jsonify(result)

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
        playlist_id = request.args.get("playlist", "")
        return render_template(
            "sleep.html",
            session_id=session_id,
            track_src=track_src,
            track_title=track_title,
            playlist_id=playlist_id,
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
        from db.users import get_persona
        data = request.get_json(force=True)
        uid = get_user_id()
        mood = data.get("mood", "calm")
        plan = {
            "soundscape_id": data.get("soundscape_id"),
            "soundscape_title": data.get("soundscape_title"),
            "soundscape_src": data.get("soundscape_src"),
            "duration_target_hours": data.get("duration_hours", 7.5),
            "wind_down": data.get("wind_down", ""),
            "mood": mood,
        }

        playlist_data = None
        playlist_id = None
        if data.get("use_playlist", True):
            from audio.playlist import build_playlist
            persona = get_persona(uid)
            playlist_data = build_playlist(mood, persona, uid)
            if playlist_data:
                playlist_id = playlist_data.get("playlist_id")
                if playlist_data["tracks"]:
                    first = playlist_data["tracks"][0]
                    plan["soundscape_id"] = first.get("track_id")
                    plan["soundscape_title"] = first.get("title")
                    plan["soundscape_src"] = first.get("src")

        session_id = create_session(uid, plan, playlist_id=playlist_id)
        if session_id:
            resp = {"session_id": session_id}
            if playlist_data:
                resp["playlist"] = playlist_data
            return jsonify(resp)
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
            metrics = data.get("metrics", {})
            review_session(sid, rating=rating, notes=notes, metrics=metrics)
        return jsonify({"status": "ok"})

    @app.route("/api/sleep/review-schema")
    @require_auth
    def api_sleep_review_schema():
        from db.sessions import VALID_REVIEW_METRICS
        return jsonify({"metrics": VALID_REVIEW_METRICS})

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

    @app.route("/api/sleep/insights")
    @require_auth
    def api_sleep_insights():
        from db.insights import get_user_sleep_insights
        days = request.args.get("days", 30, type=int)
        days = max(7, min(days, 180))
        return jsonify(get_user_sleep_insights(get_user_id(), days=days))

    # ───── Calendar / Journal ─────

    @app.route("/api/sleep/calendar")
    @require_auth
    def api_sleep_calendar():
        from db.sessions import get_sessions_for_month
        uid = get_user_id()
        year = request.args.get("year", datetime.now().year, type=int)
        month = request.args.get("month", datetime.now().month, type=int)
        sessions = get_sessions_for_month(uid, year, month)
        return jsonify({"year": year, "month": month, "sessions": sessions})

    @app.route("/api/sleep/factors", methods=["POST"])
    @require_auth
    def api_sleep_factors():
        from db.sessions import update_session_factors
        data = request.get_json(force=True)
        sid = data.get("session_id")
        factors = data.get("factors", [])
        if not sid:
            return jsonify({"error": "session_id required"}), 400
        if update_session_factors(sid, factors):
            return jsonify({"status": "ok"})
        return jsonify({"error": "Could not update"}), 400

    # ───── Scene Routes ─────

    @app.route("/api/scenes/cosmos")
    def api_scenes_cosmos():
        from web.scenes import get_apod_collection
        images = get_apod_collection(count=20)
        if images:
            return jsonify({"images": images})
        from web.scenes import get_apod
        single = get_apod()
        if single:
            return jsonify({"images": [{"url": single["url"], "title": single.get("title", "")}]})
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

    # ───── User Preferences ─────

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

    # ───── Tier / Credits / Packs ─────

    @app.route("/api/user/tier")
    @require_auth
    def api_user_tier():
        from db.tiers import get_user_tier
        return jsonify(get_user_tier(get_user_id()))

    @app.route("/api/user/credits/add", methods=["POST"])
    @require_auth
    def api_user_credits_add():
        from db.tiers import add_credits
        data = request.get_json(force=True)
        amount = int(data.get("amount", 0))
        if amount <= 0:
            return jsonify({"error": "Invalid amount"}), 400
        balance = add_credits(get_user_id(), amount)
        return jsonify({"balance": balance, "added": amount})

    @app.route("/api/user/set-admin", methods=["POST"])
    @require_auth
    def api_user_set_admin():
        from db.tiers import set_admin
        set_admin(get_user_id())
        return jsonify({"status": "ok"})

    @app.route("/api/packs")
    def api_packs():
        from db.packs import get_all_packs
        return jsonify(get_all_packs())

    @app.route("/api/packs/<slug>/purchase", methods=["POST"])
    @require_auth
    def api_pack_purchase(slug):
        from db.packs import purchase_pack
        result = purchase_pack(get_user_id(), slug)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)

    # ───── Playlist ─────

    @app.route("/api/playlist/<playlist_id>")
    @require_auth
    def api_playlist_get(playlist_id):
        from audio.playlist import get_playlist
        pl = get_playlist(playlist_id)
        if not pl:
            return jsonify({"error": "Playlist not found"}), 404
        return jsonify(pl)

    @app.route("/api/playlist/<playlist_id>/progress", methods=["POST"])
    @require_auth
    def api_playlist_progress(playlist_id):
        from audio.playlist import update_playlist_progress
        data = request.get_json(force=True)
        update_playlist_progress(playlist_id, data.get("tracks_played", 0))
        return jsonify({"status": "ok"})

    return app
