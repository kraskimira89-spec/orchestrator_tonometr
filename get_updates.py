"""
Читает getUpdates Telegram Bot API и печатает user_id пользователей, писавших /start.
Нужен токен бота (TELEGRAM_BOT_TOKEN или MAX_BOT_TOKEN, если бот — в Telegram).

Запуск из корня проекта: python get_updates.py
"""
import os
import sys

import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, ".env"))


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("MAX_BOT_TOKEN") or ""
    if not token.strip():
        print("❌ Задайте TELEGRAM_BOT_TOKEN или MAX_BOT_TOKEN в .env")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{token.strip()}/getUpdates"
    try:
        r = requests.get(url, timeout=15)
    except requests.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        sys.exit(1)

    if r.status_code != 200:
        print(f"❌ HTTP {r.status_code}: {r.text}")
        sys.exit(1)

    data = r.json()
    if not data.get("ok"):
        print(f"❌ Ответ API: {data}")
        sys.exit(1)

    seen = {}
    for upd in data.get("result", []):
        msg = upd.get("message") or upd.get("edited_message") or {}
        text = (msg.get("text") or "").strip()
        if text.split()[0:1] != ["/start"] and not text.startswith("/start "):
            continue
        user = msg.get("from") or {}
        uid = user.get("id")
        if uid is None:
            continue
        uname = user.get("username") or ""
        first = user.get("first_name") or ""
        last = user.get("last_name") or ""
        label = f"{first} {last}".strip() or uname or "?"
        seen[uid] = label

    if not seen:
        print("Нет сообщений с /start в последней выборке getUpdates.")
        print("(Telegram отдаёт только необработанные updates — при необходимости вызовите снова.)")
        return

    print("user_id → кто написал /start")
    for uid in sorted(seen.keys()):
        print(f"  {uid}  —  {seen[uid]}")


if __name__ == "__main__":
    main()
