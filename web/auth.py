"""
Firebase Auth middleware with DEV_MODE bypass.

When DEV_MODE=true (or Firebase isn't configured), all requests get a
stable dev user identity. In production, Firebase Admin SDK verifies
the Authorization: Bearer <id-token> header.
"""

import functools
import os

from flask import g, jsonify, request


DEV_USER = {
    "uid": "dev-user-001",
    "name": "Developer",
    "email": "dev@localhost",
    "picture": None,
}

_firebase_app = None
_dev_mode = False


def init_auth(app):
    global _firebase_app, _dev_mode

    _dev_mode = os.environ.get("DEV_MODE", "").lower() in ("true", "1", "yes")

    if not _dev_mode:
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
                _dev_mode = True
                app.logger.warning("Firebase not configured — running in DEV_MODE")
        except ImportError:
            _dev_mode = True
            app.logger.warning("firebase-admin not installed — running in DEV_MODE")
        except Exception as e:
            _dev_mode = True
            app.logger.warning(f"Firebase init failed ({e}) — running in DEV_MODE")

    @app.before_request
    def _set_user():
        if _dev_mode:
            g.user = dict(DEV_USER)
            _sync_user_to_db(g.user)
            return

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            g.user = None
            return

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
        except Exception:
            g.user = None

    app.jinja_env.globals["dev_mode"] = _dev_mode


def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if _dev_mode:
            return f(*args, **kwargs)
        if not getattr(g, "user", None):
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated


def get_current_user() -> dict | None:
    return getattr(g, "user", None)


def get_user_id() -> str:
    user = get_current_user()
    return user["uid"] if user else "anonymous"


def is_dev_mode() -> bool:
    return _dev_mode


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
        _synced_users.add(uid)
    except Exception:
        pass
