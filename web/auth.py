"""
Firebase Auth middleware.

Firebase Admin SDK verifies the Authorization: Bearer <id-token> header
on every request. No bypass mode — all users must sign in.
"""

import functools
import os

from flask import g, jsonify, redirect, request, session

ADMIN_EMAILS = {"hello@pixjobs.com"}

_firebase_app = None


def init_auth(app):
    global _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            _firebase_app = firebase_admin.initialize_app(cred)
        elif os.environ.get("FIREBASE_PROJECT_ID"):
            _firebase_app = firebase_admin.initialize_app()
        else:
            app.logger.warning("Firebase not configured — auth will reject all requests")
    except ImportError:
        app.logger.warning("firebase-admin not installed — auth will reject all requests")
    except Exception as e:
        app.logger.warning(f"Firebase init failed ({e}) — auth will reject all requests")

    app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))

    @app.before_request
    def _set_user():
        # 1. Try Bearer token (API calls from JS)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                from firebase_admin import auth
                decoded = auth.verify_id_token(token, app=_firebase_app)
                g.user = {
                    "uid": decoded["uid"],
                    "name": decoded.get("name", ""),
                    "email": decoded.get("email", ""),
                    "picture": decoded.get("picture"),
                }
                _sync_user_to_db(g.user)
                return
            except Exception:
                pass

        # 2. Fall back to session cookie (page loads)
        if "user" in session:
            g.user = session["user"]
            return

        g.user = None

    @app.route("/api/auth/session", methods=["POST"])
    def create_session():
        data = request.get_json(force=True)
        token = data.get("token", "")
        if not token:
            return jsonify({"error": "No token"}), 400
        try:
            from firebase_admin import auth
            decoded = auth.verify_id_token(token, app=_firebase_app)
            user = {
                "uid": decoded["uid"],
                "name": decoded.get("name", ""),
                "email": decoded.get("email", ""),
                "picture": decoded.get("picture"),
            }
            session["user"] = user
            _sync_user_to_db(user)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 401

    @app.route("/api/auth/signout", methods=["POST"])
    def destroy_session():
        session.pop("user", None)
        return jsonify({"ok": True})


def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not getattr(g, "user", None):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or user.get("email") not in ADMIN_EMAILS:
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


def get_current_user() -> dict | None:
    return getattr(g, "user", None)


def get_user_id() -> str:
    user = get_current_user()
    return user["uid"] if user else "anonymous"


def is_admin() -> bool:
    user = get_current_user()
    return bool(user and user.get("email") in ADMIN_EMAILS)


def require_login(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Login required"}), 401
        return f(*args, **kwargs)
    return decorated


_synced_users = set()


def _sync_user_to_db(user: dict):
    uid = user.get("uid")
    if not uid or uid in _synced_users:
        return
    try:
        from db.users import upsert_user
        upsert_user(uid, email=user.get("email", ""),
                     display_name=user.get("name", ""),
                     picture=user.get("picture"))
        if user.get("email") in ADMIN_EMAILS:
            from db.tiers import set_admin
            set_admin(uid)
        _synced_users.add(uid)
    except Exception:
        pass
