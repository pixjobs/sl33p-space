import functools
import json
import os
import threading
import time
from collections import defaultdict
from datetime import date, datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from web.auth import init_auth, require_auth, require_login, require_admin, get_user_id, get_current_user, is_admin

_agent_runner = None
_seeding = False
_last_seed_check = 0.0

_rate_buckets: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()


def rate_limit(max_calls: int, window_seconds: int):
    """Simple in-memory per-user rate limiter."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            uid = get_user_id()
            key = f"{f.__name__}:{uid}"
            now = time.monotonic()
            with _rate_lock:
                bucket = _rate_buckets[key]
                cutoff = now - window_seconds
                _rate_buckets[key] = [t for t in bucket if t > cutoff]
                if len(_rate_buckets[key]) >= max_calls:
                    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
                _rate_buckets[key].append(now)
            return f(*args, **kwargs)
        return wrapper
    return decorator


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

    @app.after_request
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if os.environ.get("K_SERVICE"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.after_request
    def _maybe_seed(response):
        global _seeding, _last_seed_check
        import time
        now = time.monotonic()
        if _seeding or now - _last_seed_check < 300:
            return response
        if not os.environ.get("GOOGLE_API_KEY"):
            return response
        _last_seed_check = now
        from audio.music_gen import list_generated_music
        tracks = list_generated_music()
        if len(tracks) < 5:
            _seeding = True
            need = 5 - len(tracks)
            def _seed_bg():
                global _seeding
                try:
                    from audio.music_gen import seed_n_tracks
                    seed_n_tracks(need)
                finally:
                    _seeding = False
            threading.Thread(target=_seed_bg, daemon=True).start()
        return response

    @app.context_processor
    def _inject_globals():
        cfg = {
            "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
            "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
            "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
            "appId": os.environ.get("FIREBASE_APP_ID", ""),
        }
        firebase_config = cfg if cfg["apiKey"] else None
        return {"firebase_config": firebase_config, "is_admin": is_admin()}

    @app.route("/healthz")
    def healthz():
        return "ok", 200

    @app.route("/")
    def index():
        user = get_current_user()
        if user:
            return redirect(url_for("plan"))
        return render_template("welcome.html")

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/privacy")
    def privacy():
        return render_template("legal.html", page="privacy")

    @app.route("/terms")
    def terms():
        return render_template("legal.html", page="terms")

    @app.route("/plan")
    @require_auth
    def plan():
        from audio.music_gen import list_generated_music, get_preset_prompts
        from db.sessions import get_pending_review, get_recent_sessions, get_sleep_stats, get_active_session
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

        db_user = get_user(uid)
        prefs = (db_user or {}).get("preferences", {})
        persona = prefs.get("persona")
        tracking_level = prefs.get("tracking_level", "basic")

        from db.tiers import get_user_tier, get_pending_gifts
        user_tier = get_user_tier(uid)
        pending_gifts = get_pending_gifts(uid)
        insights = get_user_sleep_insights(uid)
        try:
            from db.assets import get_cached_apod
            from db import get_db
            cached = get_cached_apod(date.today().isoformat()) if get_db() else None
            if cached and cached.get("media_type") == "image":
                apod = {"url": cached.get("hdurl") or cached.get("url"), "title": cached.get("title", ""), "explanation": cached.get("explanation", "")}
            else:
                apod = None
        except Exception:
            apod = None

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
            active_session=get_active_session(uid),
            apod=apod,
            pending_gifts=pending_gifts,
            uid=uid,
        )

    @app.route("/media/music/<path:filename>")
    def serve_music(filename):
        music_dir = os.path.abspath("data/music")
        response = send_from_directory(music_dir, filename)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Expose-Headers'] = 'Content-Length'
        return response

    # ───── Feedback ─────

    @app.route("/api/feedback", methods=["POST"])
    @require_auth
    @rate_limit(max_calls=10, window_seconds=60)
    def api_feedback():
        from db.feedback import submit_feedback
        data = request.get_json(force=True)
        feedback_type = data.get("type", "other")
        message = data.get("message", "")
        context = data.get("context", {})
        context["page"] = context.get("page", request.referrer or "")
        uid = get_user_id()
        fid = submit_feedback(uid, feedback_type, message, context)
        if fid:
            return jsonify({"status": "ok", "id": fid})
        return jsonify({"error": "Invalid feedback type"}), 400

    # ───── Chat ─────

    @app.route("/api/chat", methods=["POST"])
    @require_auth
    @rate_limit(max_calls=20, window_seconds=60)
    def api_chat():
        from db.tiers import check_chat_allowance
        data = request.get_json(force=True)
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "Empty message"}), 400
        uid = get_user_id()
        allowed, remaining, limit = check_chat_allowance(uid)
        if not allowed:
            return jsonify({"error": "Daily chat limit reached. Sleep longer to earn more!", "remaining": 0, "limit": limit}), 429
        if _agent_runner:
            response = _agent_runner(message, uid)
            return jsonify({"response": response, "remaining": remaining - 1})
        return jsonify({"response": "Agent not configured. Set GOOGLE_API_KEY to enable.", "remaining": remaining - 1})

    # ───── Music Routes ─────

    @app.route("/api/music/generate", methods=["POST"])
    @require_login
    @rate_limit(max_calls=5, window_seconds=3600)
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
    @require_auth
    def api_music_library():
        scope = request.args.get("scope", "all")
        uid = get_user_id()
        if scope == "mine" and uid != "anonymous":
            from db.tracks import get_tracks_for_user
            from audio.music_gen import format_track_entry
            return jsonify([format_track_entry(t) for t in get_tracks_for_user(uid)])
        if scope == "public":
            from db.tracks import get_public_tracks
            from audio.music_gen import format_track_entry
            return jsonify([format_track_entry(t) for t in get_public_tracks()])
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
    @require_auth
    def api_music_archive_list():
        from audio.music_gen import list_archived_music
        return jsonify(list_archived_music())

    @app.route("/api/music/suggest")
    @require_auth
    @rate_limit(max_calls=10, window_seconds=60)
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
    @require_auth
    @rate_limit(max_calls=10, window_seconds=60)
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
        mood = request.args.get("mood", "calm")
        return render_template(
            "sleep.html",
            session_id=session_id,
            track_src=track_src,
            track_title=track_title,
            playlist_id=playlist_id,
            mood=mood,
        )

    @app.route("/api/sleep/recommend", methods=["POST"])
    @require_auth
    @rate_limit(max_calls=10, window_seconds=60)
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
                model_name = _load_config().get("agent", {}).get("model", "gemini-flash-latest")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"system_instruction": "You are a sleep coach. Be concise.", "temperature": 0.7},
                )
                try:
                    from db.usage import log_api_usage
                    log_api_usage(user_id=uid, service="gemini", model=model_name,
                                  cost_usd=0.001, metadata={"purpose": "sleep_recommendation"})
                except Exception:
                    pass
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

    @app.route("/api/sleep/log", methods=["POST"])
    @require_auth
    def api_sleep_log():
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        from db.sessions import create_manual_session
        data = request.get_json(force=True)
        uid = get_user_id()
        mood = data.get("mood", "calm")
        now = _dt.now(_tz.utc)

        bed_str = data.get("bed_time", "23:00")
        wake_str = data.get("wake_time", "07:00")
        try:
            bh, bm = int(bed_str.split(":")[0]), int(bed_str.split(":")[1])
            wh, wm = int(wake_str.split(":")[0]), int(wake_str.split(":")[1])
        except (ValueError, IndexError):
            return jsonify({"error": "Invalid time format"}), 400

        bed_time = now.replace(hour=bh, minute=bm, second=0, microsecond=0)
        wake_time = now.replace(hour=wh, minute=wm, second=0, microsecond=0)
        if bed_time >= wake_time:
            bed_time -= _td(days=1)

        sid = create_manual_session(uid, bed_time, wake_time, mood)
        return jsonify({"session_id": sid, "status": "ok"})

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
            start_session(sid, track=track, user_id=get_user_id())
        return jsonify({"status": "ok"})

    @app.route("/api/sleep/end", methods=["POST"])
    @require_auth
    def api_sleep_end():
        from db.sessions import end_session, get_active_session
        from db.tiers import award_sleep_bonus
        data = request.get_json(force=True)
        uid = get_user_id()
        sid = data.get("session_id")
        if not sid:
            session = get_active_session(uid)
            sid = session["_id"] if session else None
        chat_bonus = 0
        if sid:
            end_session(sid, user_id=uid)
            from db import get_db
            db = get_db()
            if db:
                from bson import ObjectId
                ended = db.sleep_sessions.find_one({"_id": ObjectId(sid)})
                dur = (ended or {}).get("actual", {}).get("duration_minutes", 0) or 0
                chat_bonus = award_sleep_bonus(uid, dur)
        return jsonify({"status": "ok", "chat_bonus": chat_bonus})

    @app.route("/api/sleep/review", methods=["POST"])
    @require_auth
    def api_sleep_review():
        from db.sessions import review_session, skip_review, update_session_factors
        data = request.get_json(force=True)
        sid = data.get("session_id")
        if not sid:
            return jsonify({"error": "session_id required"}), 400
        uid = get_user_id()
        if data.get("skip"):
            skip_review(sid, user_id=uid)
        else:
            rating = int(data.get("rating", 3))
            metrics = data.get("metrics") or None
            notes = data.get("notes") or ""
            review_session(sid, rating=rating, notes=notes, metrics=metrics, user_id=uid)
            factors = data.get("factors")
            if factors is not None:
                update_session_factors(sid, factors, user_id=uid)
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
        if update_session_factors(sid, factors, user_id=get_user_id()):
            return jsonify({"status": "ok"})
        return jsonify({"error": "Could not update"}), 400

    @app.route("/api/sleep/notes", methods=["POST"])
    @require_auth
    def api_sleep_notes():
        from db.sessions import update_session_notes
        data = request.get_json(force=True)
        sid = data.get("session_id")
        notes = data.get("notes", "")
        if not sid:
            return jsonify({"error": "session_id required"}), 400
        if update_session_notes(sid, notes, user_id=get_user_id()):
            return jsonify({"status": "ok"})
        return jsonify({"error": "Could not update"}), 400

    @app.route("/api/sleep/delete", methods=["POST"])
    @require_auth
    def api_sleep_delete():
        from db.sessions import delete_session
        data = request.get_json(force=True)
        sid = data.get("session_id")
        if not sid:
            return jsonify({"error": "session_id required"}), 400
        uid = get_user_id()
        if delete_session(sid, uid):
            return jsonify({"status": "ok"})
        return jsonify({"error": "Could not delete"}), 400

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
                response = send_from_directory(os.path.join(scenes_dir, theme_dir), filename)
                response.headers['Access-Control-Allow-Origin'] = '*'
                return response
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

    @app.route("/api/user/timezone", methods=["POST"])
    @require_auth
    def api_user_timezone():
        data = request.get_json(force=True)
        tz = data.get("timezone", "")
        if tz and len(tz) < 50:
            from db.users import update_timezone
            update_timezone(get_user_id(), tz)
        return jsonify({"status": "ok"})

    # ───── Tier / Credits / Packs ─────

    @app.route("/api/user/gifts/dismiss", methods=["POST"])
    @require_auth
    def api_user_gifts_dismiss():
        from db.tiers import mark_gifts_seen
        mark_gifts_seen(get_user_id())
        return jsonify({"status": "ok"})

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
    @require_admin
    def api_user_set_admin():
        from db.tiers import set_admin
        data = request.get_json(force=True)
        target_uid = data.get("uid")
        if not target_uid:
            return jsonify({"error": "uid required"}), 400
        set_admin(target_uid)
        return jsonify({"status": "ok", "uid": target_uid})

    @app.route("/api/user/referral")
    @require_auth
    def api_user_referral():
        from db.tiers import get_referral_stats
        stats = get_referral_stats(get_user_id())
        return jsonify(stats)

    @app.route("/api/user/redeem-referral", methods=["POST"])
    @require_auth
    def api_user_redeem_referral():
        from db.tiers import redeem_referral
        data = request.get_json(force=True)
        code = data.get("code", "").strip()
        if not code:
            return jsonify({"error": "No referral code"}), 400
        ok, msg = redeem_referral(code, get_user_id())
        if ok:
            return jsonify({"status": "ok"})
        return jsonify({"error": msg}), 400

    @app.route("/refer/<code>")
    def referral_redirect(code):
        return redirect(f"/?ref={code}")

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

    # ───── Admin Dashboard ─────

    @app.route("/admin")
    @require_admin
    def admin_dashboard():
        from db.admin import get_platform_stats
        return render_template("admin.html", stats=get_platform_stats())

    @app.route("/admin/compliance")
    @require_admin
    def admin_compliance():
        return render_template("admin_compliance.html")

    @app.route("/api/admin/stats")
    @require_admin
    def api_admin_stats():
        from db.admin import get_platform_stats
        return jsonify(get_platform_stats())

    @app.route("/api/admin/users")
    @require_admin
    def api_admin_users():
        from db.admin import get_user_list
        page = request.args.get("page", 1, type=int)
        return jsonify(get_user_list(page=page))

    @app.route("/api/admin/usage")
    @require_admin
    def api_admin_usage():
        from db.admin import get_usage_summary
        days = request.args.get("days", 30, type=int)
        days = max(1, min(days, 180))
        return jsonify(get_usage_summary(days=days))

    @app.route("/api/admin/tracks")
    @require_admin
    def api_admin_tracks():
        from db.admin import get_track_list
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)
        per_page = max(1, min(per_page, 100))
        return jsonify(get_track_list(page=page, per_page=per_page))

    @app.route("/api/admin/gift-credits", methods=["POST"])
    @require_admin
    def api_admin_gift_credits():
        from db.tiers import gift_credits
        data = request.get_json(force=True)
        target_uid = data.get("uid")
        amount = int(data.get("amount", 0))
        if not target_uid:
            return jsonify({"error": "uid required"}), 400
        if amount < 1 or amount > 10:
            return jsonify({"error": "Amount must be 1-10"}), 400
        user = get_current_user()
        from_name = (user.get("name", "") or "").split()[0] if user else "Admin"
        new_balance = gift_credits(get_user_id(), target_uid, amount, from_name)
        return jsonify({"status": "ok", "new_balance": new_balance})

    @app.route("/api/admin/set-tier", methods=["POST"])
    @require_admin
    def api_admin_set_tier():
        from db.tiers import set_user_tier
        data = request.get_json(force=True)
        uid = data.get("uid")
        tier = data.get("tier")
        if not uid or tier not in ("free", "plus", "admin"):
            return jsonify({"error": "Invalid uid or tier"}), 400
        set_user_tier(uid, tier)
        return jsonify({"status": "ok", "tier": tier})

    @app.route("/api/admin/seed", methods=["POST"])
    @require_admin
    def api_admin_seed():
        from audio.music_gen import seed_n_tracks
        data = request.get_json(force=True) if request.is_json else {}
        n = min(data.get("n", 3), 10)
        result = seed_n_tracks(n=n)
        return jsonify(result)

    return app
