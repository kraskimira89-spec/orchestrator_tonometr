"""
Читает GET /updates у MAX Bot API и выводит таблицу user_id → имя в MAX.

Требования в .env:
  MAX_BOT_TOKEN=<токен бота>
  (опционально) MAX_ADMIN_USER_ID — для справки в подсказках

Запуск из корня проекта: python get_updates.py

Порядок:
  1. Каждый ответственный пишет боту любое сообщение или /start в MAX.
  2. Запускаете этот скрипт.
  3. Вносите user_id в GUI: «Ответственные» → сохранить.
"""
import os
import sys

import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, ".env"))

MAX_API_URL = "https://platform-api.max.ru"


def _sender_label(sender: dict) -> str:
    if not sender:
        return "—"
    first = (sender.get("first_name") or "").strip()
    last = (sender.get("last_name") or "").strip()
    name = f"{first} {last}".strip()
    if name:
        return name
    un = (sender.get("username") or "").strip()
    if un:
        return f"@{un}" if not un.startswith("@") else un
    legacy = (sender.get("name") or "").strip()
    return legacy or "—"


def _iter_updates_payload(data: dict):
    """Достаёт список updates из ответа API (на случай разных обёрток)."""
    if not isinstance(data, dict):
        return []
    if "updates" in data:
        return data["updates"] or []
    return []


def main():
    token = (os.getenv("MAX_BOT_TOKEN") or "").strip()
    if not token:
        print("❌ Задайте MAX_BOT_TOKEN в .env")
        sys.exit(1)

    url = f"{MAX_API_URL}/updates"
    params = {"limit": 100}
    try:
        r = requests.get(
            url,
            headers={"Authorization": token},
            params=params,
            timeout=90,
        )
    except requests.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        sys.exit(1)

    if r.status_code != 200:
        print(f"❌ HTTP {r.status_code}: {r.text}")
        sys.exit(1)

    try:
        data = r.json()
    except ValueError:
        print("❌ Ответ не JSON:", r.text[:500])
        sys.exit(1)

    updates = _iter_updates_payload(data)
    if not updates:
        print("Обновлений пока нет (список пуст).")
        print("Что сделать:")
        print("  • Пусть каждый ответственный напишет боту в MAX любое сообщение или /start.")
        print("  • Запустите скрипт снова через несколько секунд.")
        print("  • Если бот на webhook, для long polling может понадобиться отключить webhook в кабинете MAX.")
        return

    seen: dict[int, str] = {}

    for upd in updates:
        if not isinstance(upd, dict):
            continue
        msg = upd.get("message")
        if not isinstance(msg, dict):
            continue
        sender = msg.get("sender")
        if not isinstance(sender, dict):
            continue
        if sender.get("is_bot"):
            continue
        uid = sender.get("user_id")
        if uid is None:
            continue
        try:
            uid_int = int(uid)
        except (TypeError, ValueError):
            continue
        label = _sender_label(sender)
        seen[uid_int] = label

    if not seen:
        print("В последней выборке нет сообщений от пользователей (только боты или пустые sender).")
        print("Напишите боту из MAX с личного аккаунта и запустите скрипт снова.")
        return

    print("user_id (MAX)  →  Имя в MAX")
    print("-" * 50)
    for uid in sorted(seen.keys()):
        print(f"  {uid:<12}    {seen[uid]}")


if __name__ == "__main__":
    main()
