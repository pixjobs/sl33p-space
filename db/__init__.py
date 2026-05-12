import logging
import os

_client = None
_db = None
_warned = False

log = logging.getLogger(__name__)


def get_db():
    global _client, _db, _warned
    if _db is not None:
        return _db

    uri = os.environ.get("MONGODB_URI")
    db_name = os.environ.get("MONGODB_DATABASE", "sl33p-space")

    if not uri:
        if not _warned:
            log.warning("MONGODB_URI not set — running without persistence")
            _warned = True
        return None

    try:
        import certifi

        # pyopenssl 26.x removed X509.get_extension() which pymongo's
        # OCSP code still calls. Force pymongo to use stdlib ssl instead.
        import pymongo.ssl_support as _ss
        _ss._pyssl = None
        _ss.HAVE_PYSSL = False

        from pymongo import MongoClient
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000,
                              tlsCAFile=certifi.where())
        _client.admin.command("ping")
        _db = _client[db_name]
        log.info("Connected to MongoDB: %s", db_name)
        return _db
    except Exception as e:
        if not _warned:
            log.warning("MongoDB connection failed (%s) — running without persistence", e)
            _warned = True
        return None
