"""
Модуль отправки уведомлений через MAX Bot API.
Отправляет напоминания ответственным об истечении сроков поверки.
"""
import json
import os
import sys
import time as _time
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

MAX_API_URL = "https://platform-api.max.ru"

from db.database import get_all_devices, get_connection  # noqa: E402

# #region agent log
_GCID_DBG_LEFT = 12


def _agent_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    try:
        log_path = os.path.join(PROJECT_ROOT, "debug-409b57.log")
        line = json.dumps(
            {
                "sessionId": "409b57",
                "hypothesisId": hypothesis_id,
                "location": location,
                "message": message,
                "data": data,
                "timestamp": int(_time.time() * 1000),
            },
            ensure_ascii=False,
        )
        with open(log_path, "a", encoding="utf-8") as _lf:
            _lf.write(line + "\n")
    except Exception:
        pass


# #endregion


def send_message(chat_id: str, text: str) -> bool:
    """Отправляем сообщение через MAX Bot API.

    Согласно документации: user_id передаётся как query-параметр,
    текст — в теле запроса.
    """
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
            params={"user_id": int(chat_id)},   # ← user_id в URL
            json={"text": text},                 # ← только текст в теле
            timeout=10,
        )
        if r.status_code == 200:
            return True
        else:
            print(f"❌ MAX API {r.status_code}: {r.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Нет соединения с MAX API.")
        return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
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
    global _GCID_DBG_LEFT

    resp_fio = device.get("responsible_fio") or ""
    if not resp_fio:
        out = ADMIN_CHAT_ID or None
        # #region agent log
        if _GCID_DBG_LEFT > 0:
            _GCID_DBG_LEFT -= 1
            _agent_log(
                "H4",
                "notifier.py:get_chat_id_for_device",
                "resolved",
                {
                    "source": "empty_fio_admin",
                    "result_len": len(out) if out else 0,
                    "result_isdigit": out.isdigit() if out else False,
                },
            )
        # #endregion
        return out

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT max_chat_id FROM users WHERE name = ? AND max_chat_id IS NOT NULL",
        (resp_fio,),
    )
    row = cur.fetchone()
    conn.close()

    if row and row[0]:
        out = str(row[0])
        # #region agent log
        if _GCID_DBG_LEFT > 0:
            _GCID_DBG_LEFT -= 1
            _agent_log(
                "H4",
                "notifier.py:get_chat_id_for_device",
                "resolved",
                {
                    "source": "users.max_chat_id",
                    "fio_len": len(resp_fio.strip()),
                    "result_len": len(out),
                    "result_isdigit": out.isdigit(),
                },
            )
        # #endregion
        return out

    # если у ответственного нет chat_id — уведомление идёт администратору
    out = ADMIN_CHAT_ID or None
    # #region agent log
    if _GCID_DBG_LEFT > 0:
        _GCID_DBG_LEFT -= 1
        _agent_log(
            "H4",
            "notifier.py:get_chat_id_for_device",
            "resolved",
            {
                "source": "admin_fallback_no_user_chat",
                "fio_len": len(resp_fio.strip()),
                "result_len": len(out) if out else 0,
                "result_isdigit": out.isdigit() if out else False,
            },
        )
    # #endregion
    return out


def check_and_notify(dry_run: bool = False) -> dict:
    """
    Проверяет все приборы и отправляет уведомления.

    dry_run=True — только подготавливает сообщения, не отправляет.
    Возвращает статистику: {'sent': N, 'skipped': M, 'errors': K}
    """
    # #region agent log
    _agent_log(
        "H2",
        "notifier.py:check_and_notify:entry",
        "config",
        {
            "dry_run": dry_run,
            "admin_chat_id_configured": bool((ADMIN_CHAT_ID or "").strip()),
            "admin_chat_id_len": len((ADMIN_CHAT_ID or "").strip()),
            "token_configured": bool((MAX_BOT_TOKEN or "").strip()),
        },
    )
    # #endregion
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
