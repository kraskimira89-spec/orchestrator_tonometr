"""
Уведомления через MAX Bot API: приборы группируются по ответственному,
для каждого берётся max_user_id из responsible_persons; если нет — рассылка на MAX_ADMIN_USER_ID.
"""
import os
import sys
from collections import defaultdict
from datetime import date, datetime

import requests
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
MAX_ADMIN_USER_ID = (os.getenv("MAX_ADMIN_USER_ID") or os.getenv("ADMIN_CHAT_ID") or "").strip()
NOTIFY_DAYS_1 = int(os.getenv("NOTIFY_DAYS_1", "60"))
NOTIFY_DAYS_2 = int(os.getenv("NOTIFY_DAYS_2", "7"))

MAX_API_URL = "https://platform-api.max.ru"

from db.database import (  # noqa: E402
    get_all_devices,
    get_connection,
    get_max_user_id_for_fio,
)


def send_message(chat_id: str, text: str) -> bool:
    """Отправка сообщения в MAX: user_id в query, текст в JSON."""
    if not MAX_BOT_TOKEN:
        print("❌ MAX_BOT_TOKEN не задан в .env")
        return False

    try:
        r = requests.post(
            f"{MAX_API_URL}/messages",
            headers={
                "Authorization": MAX_BOT_TOKEN,
                "Content-Type": "application/json",
            },
            params={"user_id": int(chat_id)},
            json={"text": text},
            timeout=10,
        )
        if r.status_code == 200:
            return True
        print(f"❌ MAX API {r.status_code}: {r.text}")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Нет соединения с MAX API.")
        return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def days_until(expiry_str: str) -> int | None:
    try:
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        return (expiry - date.today()).days
    except Exception:
        return None


def _admin_chat_id() -> str | None:
    return MAX_ADMIN_USER_ID if MAX_ADMIN_USER_ID else None


def resolve_recipient_user_id(responsible_fio: str) -> str | None:
    """
    MAX user_id для ответственного: из responsible_persons,
    иначе администратор MAX_ADMIN_USER_ID.
    Пустое ФИО — сразу администратор.
    """
    fio = (responsible_fio or "").strip()
    if not fio:
        return _admin_chat_id()

    uid = get_max_user_id_for_fio(fio)
    if uid is not None:
        return str(uid)
    return _admin_chat_id()


def _device_notice_lines(device: dict, urgency: str, detail: str, expiry_fmt: str) -> list[str]:
    inv = device.get("inventory_number") or "—"
    loc = device.get("location") or "—"
    resp = device.get("responsible_fio") or "не указан"
    dev_type = device.get("type") or "Прибор"
    return [
        f"{urgency}",
        f"📋 {dev_type}: {inv}",
        f"📍 {loc}",
        f"👤 Ответственный: {resp}",
        f"📅 Дата окончания: {expiry_fmt}",
        f"⏳ {detail.capitalize()}",
        "━━━━━━━━━━━━━━━━━━",
    ]


def check_and_notify(dry_run: bool = False) -> dict:
    """
    Уведомления сгруппированы по получателю (один user_id — одно сообщение со всеми приборами).
    """
    devices = get_all_devices()
    stats = {"sent": 0, "skipped": 0, "errors": 0, "messages": []}

    # (fio_key, recipient_id) -> список фрагментов
    # fio_key — для отладки; recipient_id — куда слать
    groups: dict[tuple[str, str], list] = defaultdict(list)

    for device in devices:
        expiry = device.get("expiry_date")
        if not expiry:
            stats["skipped"] += 1
            continue

        d = days_until(expiry)
        if d is None:
            stats["skipped"] += 1
            continue

        if d < 0:
            urgency = "🔴 ПРОСРОЧЕНО"
            detail = f"срок истёк {abs(d)} дн. назад"
        elif d <= NOTIFY_DAYS_2:
            urgency = "🔴 СРОЧНО"
            detail = f"до окончания {d} дн."
        elif d <= NOTIFY_DAYS_1:
            urgency = "🟡 ВНИМАНИЕ"
            detail = f"до окончания {d} дн."
        else:
            stats["skipped"] += 1
            continue

        fio = (device.get("responsible_fio") or "").strip()
        fio_key = fio if fio else "__пусто__"
        recipient = resolve_recipient_user_id(fio)
        if not recipient:
            stats["errors"] += 1
            continue

        expiry_fmt = datetime.strptime(expiry, "%Y-%m-%d").strftime("%d.%m.%Y")
        groups[(fio_key, recipient)].append(
            (device, urgency, detail, expiry_fmt)
        )

    today_str = date.today().strftime("%d.%m.%Y")

    for (_fio_key, chat_id), items in groups.items():
        blocks = []
        for device, urgency, detail, expiry_fmt in items:
            blocks.extend(_device_notice_lines(device, urgency, detail, expiry_fmt))

        header = (
            f"Напоминания о поверке ({len(items)} шт.)\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        text = header + "\n".join(blocks) + f"Оркестратор Поверки | {today_str}"

        for device, _u, _d, _e in items:
            stats["messages"].append(
                {
                    "chat_id": chat_id,
                    "text": text,
                    "device_id": device.get("id"),
                }
            )

        if dry_run:
            stats["sent"] += len(items)
            continue

        ok = send_message(chat_id, text)
        if ok:
            conn = get_connection()
            cur = conn.cursor()
            for device, _u, _d, _e in items:
                cur.execute(
                    """
                    INSERT INTO notification_log
                        (device_id, channel, message, status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (device.get("id"), "MAX", text, "sent"),
                )
                stats["sent"] += 1
            conn.commit()
            conn.close()
        else:
            stats["errors"] += len(items)

    return stats


def send_notifications():
    """Точка входа для планировщика и скриптов."""
    return check_and_notify(dry_run=False)


if __name__ == "__main__":
    print("🔔 Запуск проверки уведомлений...\n")
    result = send_notifications()
    print(f"✅ Отправлено:  {result['sent']}")
    print(f"⏭  Пропущено:  {result['skipped']}")
    print(f"❌ Ошибок:     {result['errors']}")
    if result["messages"]:
        print(f"\nЗаписей в очереди уведомлений: {len(result['messages'])}")
