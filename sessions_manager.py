# sessions_manager.py
import json
import os
from datetime import datetime, timedelta
from threading import RLock

DB_FILE = "users_db.json"
DB_LOCK = RLock()

# ======================
# STEPS
# ======================
STEP_ASK_PHONE = 1
STEP_ASK_CODE = 2
STEP_MENU = 3
STEP_ASK_EMAIL = 4

# ======================
# CONFIG
# ======================
TRIAL_DAYS = 31  # 👈 altere aqui quando quiser

# ======================
# HELPERS
# ======================
def has_valid_plan(session: dict) -> bool:
    """
    Retorna True se o usuário tem plano ou teste válido
    """
    exp = session.get("expiration")
    if not exp:
        return False

    try:
        return datetime.now() < datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return False


# ======================
# DB CORE
# ======================
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


# ======================
# SESSION
# ======================
def get_user_session(user_id, create_if_missing=True):
    db = load_db()
    uid = str(user_id)

    if uid not in db:
        if not create_if_missing:
            return None

        # 🎁 usuário novo → ganha teste
        expiration = (datetime.now() + timedelta(days=TRIAL_DAYS)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        db[uid] = {
            "step": 0,
            "phone": "",
            "token": "",
            "wallet": "",

            # ⏳ validade (teste ou plano)
            "expiration": expiration,

            # 🔐 permissões
            "is_admin": False,

            # 🎁 controle de teste
            "is_trial": True,          # este usuário é teste
            "trial_notified": False,   # ainda não avisamos do teste

            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        save_db(db)

    return db[uid]


def update_user_session(user_id, updates: dict):
    db = load_db()
    uid = str(user_id)

    # 🔒 garante estrutura completa
    if uid not in db:
        _ = get_user_session(user_id)

        # recarrega após criação
        db = load_db()

    db[uid].update(updates)
    save_db(db)


def delete_user_session(user_id):
    db = load_db()
    db.pop(str(user_id), None)
    save_db(db)