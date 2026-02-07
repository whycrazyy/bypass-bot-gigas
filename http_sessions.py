import requests
from threading import RLock
from headers import HEADERS_WEB

_sessions = {}
_lock = RLock()

def get_http_session(user_id, mode="web"):
    with _lock:
        key = f"{user_id}:{mode}"

        if key not in _sessions:
            s = requests.Session()
            s.verify = False

            # 🔥 SEMPRE HEADERS WEB
            s.headers.update(HEADERS_WEB)

            _sessions[key] = s

        return _sessions[key]


def clear_http_session(user_id):
    with _lock:
        for k in list(_sessions.keys()):
            if k.startswith(f"{user_id}:"):
                _sessions.pop(k, None)