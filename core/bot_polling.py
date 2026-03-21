"""
Запускается отдельно: python core/bot_polling.py
Бот отвечает на /start и /id своим user_id.
Оставь работать в фоне пока собираешь user_id ответственных.
"""
import os
import sys
import time

import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

load_dotenv(os.path.join(ROOT, ".env"))

TOKEN = os.getenv("MAX_BOT_TOKEN", "")
BASE = "https://platform-api.max.ru"
HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json"}

marker = None  # для постраничного чтения обновлений


def _sender_display_name(sender: dict) -> str:
    first = (sender.get("first_name") or "").strip()
    last = (sender.get("last_name") or "").strip()
    name = f"{first} {last}".strip()
    if name:
        return name
    if sender.get("name"):
        return str(sender["name"]).strip()
    un = (sender.get("username") or "").strip()
    return f"@{un}" if un else "коллега"


def _message_text(msg: dict) -> str:
    body = msg.get("body")
    if not isinstance(body, dict):
        return ""
    t = body.get("text")
    return (t or "").strip().lower() if isinstance(t, str) else ""


print("Бот запущен. Ожидаю сообщения... (Ctrl+C для остановки)")

while True:
    try:
        if not TOKEN.strip():
            print("❌ MAX_BOT_TOKEN не задан в .env")
            time.sleep(30)
            continue

        params: dict = {"limit": 100, "timeout": 20}
        if marker is not None:
            params["marker"] = marker

        r = requests.get(f"{BASE}/updates", headers=HEADERS, params=params, timeout=35)
        if r.status_code != 200:
            print(f"HTTP {r.status_code}: {r.text[:500]}")
            time.sleep(5)
            continue

        data = r.json()
        for upd in data.get("updates", []) or []:
            if not isinstance(upd, dict):
                continue
            msg = upd.get("message") or {}
            if not isinstance(msg, dict):
                continue
            sender = msg.get("sender") or {}
            if not isinstance(sender, dict):
                continue
            text = _message_text(msg)
            uid = sender.get("user_id")
            name = _sender_display_name(sender)

            if sender.get("is_bot"):
                continue
            if uid is None:
                continue

            print(f"[{name}] user_id={uid}: «{text}»")

            if text in ("/start", "/id", "мой id", "id", "мой айди"):
                reply = (
                    f"Привет, {name}!\n"
                    f"Ваш MAX user_id: {uid}\n\n"
                    f"Передайте это число администратору — "
                    f"он внесёт его в систему уведомлений о поверках."
                )
                requests.post(
                    f"{BASE}/messages",
                    headers=HEADERS,
                    params={"user_id": int(uid)},
                    json={"text": reply},
                    timeout=10,
                )

        marker = data.get("marker")

    except KeyboardInterrupt:
        print("\nОстановлено.")
        break
    except Exception as e:
        print(f"Ошибка: {e}")
        time.sleep(5)
