import re
import requests
from datetime import datetime
import os
import json

# ------------------ Konfiguration ------------------

URLS = [
    "https://charge.ubitricity.com/map/DE*UBI*E10076281",
    "https://charge.ubitricity.com/map/DE*UBI*E10079698",
    "https://charge.ubitricity.com/map/DE*UBI*E10080582",
    "https://charge.ubitricity.com/map/DE*UBI*E10064840",
]

STATUS_LABELS = {
    "AVAILABLE": "✅ Verfügbar",
    "CHARGING": "⚡ Lädt",
    "INOPERATIVE": "🛠️ Nicht betriebsbereit",
    "UNKNOWN": "❓ Unbekannt / gestört",
    "OUTOFORDER": "🚫 Außer Betrieb",
    "REMOVED": "❌ Entfernt",
}

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "status_cache.json")


def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
    }

    try:
        requests.post(url, data=data, timeout=20)
    except:
        pass


def parse_address_and_statuses(html: str):
    address_match = re.search(
        r'"?street"?\s*:\s*"([^"]*)".*?"?postcode"?\s*:\s*"([^"]*)".*?"?city"?\s*:\s*"([^"]*)"',
        html,
        re.S,
    )

    if address_match:
        street = address_match.group(1)
        postcode = address_match.group(2)
        city = address_match.group(3)
        addr_str = f"{street}, {postcode} {city}"
    else:
        addr_str = "Adresse nicht gefunden"

    statuses = {}

    for match in re.finditer(
        r'([A-Za-z0-9_]+)\.id="(DE\*UBI\*[^"]+)";\1\.status="([^"]+)"',
        html,
        re.S,
    ):
        evse_id = match.group(2)
        status = match.group(3).strip().upper()
        statuses[evse_id] = status

    if not statuses:
        for match in re.finditer(
            r'"?id"?\s*:\s*"(DE\*UBI\*[^"]+)".*?"?status"?\s*:\s*"([^"]+)"',
            html,
            re.S,
        ):
            evse_id = match.group(1)
            status = match.group(2).strip().upper()
            statuses[evse_id] = status

    return addr_str, statuses


def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except:
        pass


def check_once():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cache = load_cache()
    new_cache = dict(cache)

    any_change = False

    for url in URLS:
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except:
            continue

        addr, statuses = parse_address_and_statuses(html)

        if not statuses:
            continue

        for evse_id, status in statuses.items():
            key = f"{url}|{evse_id}"
            old_status = cache.get(key)

            if old_status == status:
                continue

            any_change = True
            new_cache[key] = status

            old_str = old_status if old_status is not None else "unbekannt"
            pretty_old = STATUS_LABELS.get(old_status, old_str)
            pretty_new = STATUS_LABELS.get(status, status)

            msg = (
                f"<b>🔔 Statusänderung an der Ladesäule</b>\n\n"
                f"🆔 <b>ID:</b> {evse_id}\n"
                f"📍 <b>Adresse:</b> {addr}\n\n"
                f"📊 <b>Status alt:</b> {pretty_old}\n"
                f"📊 <b>Status neu:</b> {pretty_new}\n\n"
                f"🔗 <b>Link:</b> {url}\n"
                f"🕒 <b>Zeit:</b> {now}"
            )

            send_telegram(msg)

    save_cache(new_cache)

    if not any_change:
        msg = (
            f"<b>✅ Ubitricity-Check</b>\n\n"
            f"Es gab bei keiner überwachten Ladesäule eine Statusänderung.\n\n"
            f"🕒 <b>Letzter Check:</b> {now}"
        )
        send_telegram(msg)


if __name__ == "__main__":
    check_once()
