"""
Модуль отправки уведомлений через MAX Bot API.
Отправляет напоминания ответственным об истечении сроков поверки.
"""
import os
import sys
from datetime import date, datetime

import requests
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
NOTIFY_DAYS_1 = int(os.getenv("NOTIFY_DAYS_1", "60"))
NOTIFY_DAYS_2 = int(os.getenv("NOTIFY_DAYS_2", "7"))

MAX_API_URL = "https://botapi.max.ru"

from db.database import get_all_devices, get_connection  # noqa: E402


def send_message(chat_id: str, text: str) -> bool:
    """Отправляет сообщение через MAX Bot API."""
    if not MAX_BOT_TOKEN:
        print("❌ MAX_BOT_TOKEN не задан в .env")
        return False

    url = f"{MAX_API_URL}/messages"
    params = {"access_token": MAX_BOT_TOKEN}
    payload = {
        "recipient": {"chat_id": int(chat_id)},
        "message": {"text": text},
    }

    try:
        resp = requests.post(url, params=params, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        else:
            print(f"❌ Ошибка MAX API: {resp.status_code} — {resp.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Нет соединения с MAX API.")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False


def days_until(expiry_str: str) -> int | None:
    """Возвращает количество дней до истечения срока поверки."""
    try:
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        return (expiry - date.today()).days
    except Exception:
        return None


def get_chat_id_for_device(device: dict) -> str | None:
    """
    Возвращает chat_id ответственного из БД.
    Если не задан — возвращает ADMIN_CHAT_ID.
    """
    resp_fio = device.get("responsible_fio") or ""
    if not resp_fio:
        return ADMIN_CHAT_ID or None

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT max_chat_id FROM users WHERE name = ? AND max_chat_id IS NOT NULL",
        (resp_fio,),
    )
    row = cur.fetchone()
    conn.close()

    if row and row[0]:
        return str(row[0])

    # если у ответственного нет chat_id — уведомление идёт администратору
    return ADMIN_CHAT_ID or None


def check_and_notify(dry_run: bool = False) -> dict:
    """
    Проверяет все приборы и отправляет уведомления.

    dry_run=True — только подготавливает сообщения, не отправляет.
    Возвращает статистику: {'sent': N, 'skipped': M, 'errors': K}
    """
    devices = get_all_devices()
    stats = {"sent": 0, "skipped": 0, "errors": 0, "messages": []}

    today_str = date.today().strftime("%d.%m.%Y")

    for device in devices:
        expiry = device.get("expiry_date")
        if not expiry:
            stats["skipped"] += 1
            continue

        days = days_until(expiry)
        if days is None:
            stats["skipped"] += 1
            continue

        # определяем нужно ли уведомлять
        if days < 0:
            urgency = "🔴 ПРОСРОЧЕНО"
            detail = f"срок истёк {abs(days)} дн. назад"
        elif days <= NOTIFY_DAYS_2:
            urgency = "🔴 СРОЧНО"
            detail = f"до окончания {days} дн."
        elif days <= NOTIFY_DAYS_1:
            urgency = "🟡 ВНИМАНИЕ"
            detail = f"до окончания {days} дн."
        else:
            stats["skipped"] += 1
            continue

        inv = device.get("inventory_number") or "—"
        loc = device.get("location") or "—"
        resp = device.get("responsible_fio") or "не указан"
        expiry_fmt = datetime.strptime(expiry, "%Y-%m-%d").strftime("%d.%m.%Y")
        dev_type = device.get("type") or "Прибор"

        text = (
            f"{urgency}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 {dev_type}: {inv}\n"
            f"📍 {loc}\n"
            f"👤 Ответственный: {resp}\n"
            f"📅 Дата окончания: {expiry_fmt}\n"
            f"⏳ {detail.capitalize()}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Оркестратор Поверки | {today_str}"
        )

        chat_id = get_chat_id_for_device(device)
        if not chat_id:
            stats["errors"] += 1
            continue

        stats["messages"].append({
            "chat_id": chat_id,
            "text": text,
            "device_id": device.get("id"),
        })

        if not dry_run:
            ok = send_message(chat_id, text)
            if ok:
                # логируем в БД
                conn = get_connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO notification_log
                        (device_id, channel, message, status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (device.get("id"), "MAX", text, "sent"),
                )
                conn.commit()
                conn.close()
                stats["sent"] += 1
            else:
                stats["errors"] += 1

    return stats


if __name__ == "__main__":
    print("🔔 Запуск проверки уведомлений...\n")
    result = check_and_notify(dry_run=False)
    print(f"✅ Отправлено:  {result['sent']}")
    print(f"⏭  Пропущено:  {result['skipped']}")
    print(f"❌ Ошибок:     {result['errors']}")
    if result["messages"]:
        print(f"\nПриборы с истекающим сроком: {len(result['messages'])}")
        for m in result["messages"]:
            print(f"  device_id={m['device_id']} → chat_id={m['chat_id']}")
