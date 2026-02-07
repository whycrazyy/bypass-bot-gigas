import time
import random
import logging
import string
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from http_sessions import get_http_session
from headers import HEADERS_WEB

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# silencia warning do verify=False
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# =========================
# CONFIGURAÇÃO BASE
# =========================
BASE_API_URL = "https://api.vivofree.com.br/39dd54c0-9ea1-4708-a9c5-5120810b3b72"

HEADERS_WEB = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    # identidade Internet Grátis
    "Origin": "https://internetgratis.vivo.com.br",
    "Referer": "https://internetgratis.vivo.com.br/",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/144.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "X-API-TOKEN": "",
    "X-APP-VERSION": "3.2.12",
    "X-CHANNEL": "WEB",
    "X-CONSUMER": "VIVOREWARDS",
}

ARTEMIS_UUID = "vivo-pontos-10ad-400c-88d9-fc32e2371e36"
ACCESS_TOKEN = "4e82abb4-2718-4d65-bcd4-c4e147c3404f"
ZONE_UUID = "c0e16d43-4039-446e-a708-0bec66259111"


# =========================
# HELPERS
# =========================
def random_device_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=16))


def random_app_version():
    return f"3.{random.randint(0,9)}.{random.randint(10,99)}"


def make_request(method, url, headers, json_data=None):
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=20, verify=False)
        else:
            r = requests.post(
                url, headers=headers, json=json_data, timeout=20, verify=False
            )

        logging.info(f"[HTTP] {method} {url} -> {r.status_code}")
        return r
    except Exception as e:
        logging.error(f"[HTTP ERROR] {e}")
        return None


def _auth_headers(token=None, user_id=None):
    h = HEADERS_WEB.copy()
    if token:
        h["X-AUTHORIZATION"] = token
    if user_id:
        h["X-USER-ID"] = user_id
    return h


def _parse_json(res):
    try:
        return res.json()
    except Exception:
        return {}


# =========================
# LOGIN
# =========================


def processar_vivo_free(phone, code=None, telegram_user_id=None):
    sess = get_http_session(telegram_user_id, mode="web")

    sess.headers["X-USER-ID"] = phone
    sess.headers.pop("X-AUTHORIZATION", None)
    sess.headers.pop("X-PINCODE", None)

    if not code:
        logging.info("[SMS] user=%s phone=%s", telegram_user_id, phone)

        res = sess.post(
            f"{BASE_API_URL}/pnde",
            json={"msisdn": phone},
            timeout=20,
        )

        logging.info(
            "[SMS] status=%s cookies=%s",
            res.status_code,
            sess.cookies.get_dict(),
        )

        return {"success": res.status_code == 200}

    sess.headers["X-PINCODE"] = str(code)

    res = sess.post(
        f"{BASE_API_URL}/vapi",
        json={"token": str(code)},
        timeout=20,
    )

    token = res.headers.get("X-Authorization")
    data = _parse_json(res)

    if token:
        return {
            "success": True,
            "auth_token": token,
            "wallet_id": data.get("id") or phone,
        }

    return {"success": False}


# =========================
# CAMPANHAS
# =========================
def parse_reward(campaign):
    offers = campaign.get("benefitOffers", [])
    if not offers:
        return 0

    offer = offers[0]
    qty = float(offer.get("quantity", 0))
    unit = (offer.get("unit") or "").upper()

    # ✅ regra correta: quem manda é a UNIT, não o nome
    if unit == "GB":
        return qty * 1024
    if unit == "MB":
        return qty

    return 0


def is_valid_campaign(campaign):
    name = (campaign.get("campaignName") or "").lower()
    reward = parse_reward(campaign)

    medias = campaign.get("mainData", {}).get("media", [])
    pendentes = [m for m in medias if m.get("viewed") is not True]

    logging.info(
        f"[CAMP] '{campaign.get('campaignName')}' reward={reward}MB videos_pendentes={len(pendentes)}"
    )

    if "vivo free" in name:
        logging.info("[CAMP] ignorada: Vivo Free")
        return False
    if reward <= 0:
        logging.info("[CAMP] ignorada: reward zero")
        return False
    if not pendentes:
        logging.info("[CAMP] ignorada: sem vídeos")
        return False

    return True


def list_campaigns(token, wallet_id, telegram_user_id):
    sess = get_http_session(telegram_user_id, mode="web")

    headers = _auth_headers(token=token, user_id=wallet_id)
    headers.update(
        {
            "X-ARTEMIS-CHANNEL-UUID": ARTEMIS_UUID,
            "x-access-token": ACCESS_TOKEN,
            "X-APP-VERSION": random_app_version(),
        }
    )

    res = sess.post(
        f"{BASE_API_URL}/adserver/campaign/v3/{ZONE_UUID}?size=100",
        headers=headers,
        json={
            "userId": wallet_id,
            "contextInfo": {
                "os": "WEB",
                "brand": "Chrome",
                "model": "Desktop",
                "deviceId": random_device_id(),
                "eventDate": int(time.time() * 1000),
            },
        },
        timeout=20,
    )

    logging.info(
        "[ADS_LIST] user=%s status=%s cookies=%s",
        telegram_user_id,
        res.status_code,
        sess.cookies.get_dict(),
    )

    if res.status_code == 200:
        return _parse_json(res).get("campaigns", [])
    return []


# =========================
# COLETA
# =========================
def collect_campaigns(token, wallet_id, telegram_user_id, delay_seconds=1.0):
    sess = get_http_session(telegram_user_id, mode="web")

    headers = _auth_headers(token=token, user_id=wallet_id)
    headers.update({
        "X-ARTEMIS-CHANNEL-UUID": ARTEMIS_UUID,
        "x-access-token": ACCESS_TOKEN,
    })

    campaigns = [
        c for c in list_campaigns(token, wallet_id, telegram_user_id)
        if is_valid_campaign(c)
    ]

    logging.info(f"[COLLECT] campanhas válidas: {len(campaigns)}")

    if not campaigns:
        return 0, 0

    total_mb = 0
    completed = 0

    for camp in campaigns:
        reward_total = parse_reward(camp)

        medias = camp.get("mainData", {}).get("media", [])
        pendentes = [m for m in medias if m.get("viewed") is not True]

        if not pendentes:
            continue

        c_uuid = camp.get("campaignUuid")
        req_id = camp.get("trackingId")

        reward_por_video = reward_total / len(pendentes)

        logging.info(
            f"[COLLECT] '{camp.get('campaignName')}' "
            f"videos={len(pendentes)} reward={reward_total:.2f}MB"
        )

        for ad in pendentes:
            m_uuid = ad.get("uuid")

            # impression
            sess.post(
                f"{BASE_API_URL}/adserver/tracker"
                f"?e=impression&c={c_uuid}&u={wallet_id}"
                f"&requestId={req_id}&m={m_uuid}",
                headers=headers,
                timeout=10,
            )

            time.sleep(delay_seconds)

            # complete
            res = sess.post(
                f"{BASE_API_URL}/adserver/tracker"
                f"?e=complete&c={c_uuid}&u={wallet_id}"
                f"&requestId={req_id}&m={m_uuid}",
                headers=headers,
                timeout=10,
            )

            if res and res.status_code == 200:
                completed += 1
                total_mb += reward_por_video

    logging.info(
        f"[COLLECT][END] user={telegram_user_id} "
        f"videos_total={completed} total_mb={total_mb:.2f}"
    )

    return completed, total_mb
