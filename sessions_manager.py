# sessions_manager.py
import json
import os
from datetime import datetime, timedelta
from threading import RLock

DB_FILE = "users_db.json"
DB_LOCK = RLock()

STEP_ASK_PHONE = 1
STEP_ASK_CODE = 2
STEP_MENU = 3
STEP_ASK_EMAIL = 4

def load_db():
    with DB_LOCK:
        if not os.path.exists(DB_FILE):
            return {}
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

def save_db(data):
    with DB_LOCK:
        tmp = DB_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, DB_FILE)

def get_user_session(user_id, create_if_missing=True):
    db = load_db()
    str_id = str(user_id)

    if str_id not in db:
        if not create_if_missing:
            return None
        expiration = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        db[str_id] = {
            "step": 0, "phone": "", "token": "", "wallet": "",
            "expiration": expiration, "is_admin": False, "is_trial_used": True
        }
        save_db(db)
    return db[str_id]

def update_user_session(user_id, updates):
    db = load_db()
    str_id = str(user_id)
    if str_id not in db:
        db[str_id] = {}
    db[str_id].update(updates)
    save_db(db)

def delete_user_session(user_id):
    db = load_db()
    db.pop(str(user_id), None)
    save_db(db)