"""
Уведомления через MAX Bot API: утренняя сводная ведомость (стадии, сроки, ответственные).
Одинаковый текст сводки уходит каждому уникальному получателю (ответственный → max_user_id, иначе админ).
"""
import os
import sys
from datetime import date

import requests
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
MAX_ADMIN_USER_ID = (os.getenv("MAX_ADMIN_USER_ID") or os.getenv("ADMIN_CHAT_ID") or "").strip()

MAX_API_URL = "https://platform-api.max.ru"

from core.daily_digest import compute_digest, format_digest_plain  # noqa: E402
from db.database import (  # noqa: E402
    get_all_devices,
    get_max_user_id_for_fio,
    log_digest_notification,
    was_digest_notification_sent_today,
)

MAX_MSG_LEN = 3800
_FOOTER_RESERVE = 150


def _split_into_chunks(header: str, lines: list[str]) -> list[str]:
    limit = MAX_MSG_LEN - _FOOTER_RESERVE
    chunks: list[str] = []
    h = header.rstrip() + "\n\n"
    h_cont = header.rstrip() + " (продолжение)\n\n"
    current = h
    for line in lines:
        addition = line + "\n"
        if len(current) + len(addition) > limit:
            chunks.append(current.rstrip())
            current = h_cont + addition
        else:
            current += addition
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def send_message(chat_id: str, text: str) -> bool:
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


def _admin_chat_id() -> str | None:
    return MAX_ADMIN_USER_ID if MAX_ADMIN_USER_ID else None


def resolve_recipient_user_id(responsible_fio: str) -> str | None:
    fio = (responsible_fio or "").strip()
    if not fio:
        return _admin_chat_id()

    uid = get_max_user_id_for_fio(fio)
    if uid is not None:
        return str(uid)
    return _admin_chat_id()


def check_and_notify(dry_run: bool = False) -> dict:
    """
    Рассылка утренней сводки всем уникальным MAX-получателям из журнала приборов.
    """
    devices = get_all_devices()
    digest = compute_digest(devices)
    base_plain = format_digest_plain(digest)

    recipients: set[str] = set()
    for d in devices:
        rid = resolve_recipient_user_id((d.get("responsible_fio") or "").strip())
        if rid:
            recipients.add(rid)

    stats: dict = {
        "sent": 0,
        "skipped": 0,
        "errors": 0,
        "messages": [],
        "skipped_already_today": 0,
    }

    if not MAX_BOT_TOKEN:
        print("❌ MAX_BOT_TOKEN не задан в .env")
        stats["errors"] = 1
        return stats

    if not recipients:
        print("❌ Нет получателей MAX (укажите MAX_ADMIN_USER_ID в .env).")
        stats["errors"] = 1
        return stats

    today_str = date.today().strftime("%d.%m.%Y")
    footer = f"Оркестратор Поверки | {today_str}"

    body_lines = base_plain.split("\n")
    header = (body_lines[0] + "\n━━━━━━━━━━━━━━━━━━") if body_lines else "📊 Сводка"
    rest = body_lines[1:] if len(body_lines) > 1 else []

    def _chat_key(x: str):
        try:
            return (0, int(x))
        except ValueError:
            return (1, x)

    for chat_id in sorted(recipients, key=_chat_key):
        if was_digest_notification_sent_today("MAX_digest", chat_id):
            stats["skipped_already_today"] += 1
            print(f"  MAX: сводка для chat_id={chat_id} уже была сегодня.")
            continue

        chunks = _split_into_chunks(header, rest)
        final_parts: list[str] = []
        n = len(chunks)
        for i, body in enumerate(chunks, 1):
            suffix = f" [часть {i}/{n}]" if n > 1 else ""
            final_parts.append(f"{body}\n\n{footer}{suffix}")

        combined_for_log = "\n\n---\n\n".join(final_parts)
        stats["messages"].append(
            {"chat_id": chat_id, "text": combined_for_log, "device_id": None}
        )

        if dry_run:
            for i, part in enumerate(final_parts, 1):
                print(
                    f"[DRY RUN] → chat_id={chat_id}, часть {i}/{len(final_parts)}, "
                    f"{len(part)} симв."
                )
                print(part)
                print()
            stats["sent"] += 1
            continue

        all_ok = True
        for final_text in final_parts:
            if not send_message(chat_id, final_text):
                all_ok = False
                break

        if all_ok:
            log_digest_notification("MAX_digest", chat_id)
            stats["sent"] += 1
        else:
            stats["errors"] += 1

    return stats


def send_notifications(dry_run: bool = False):
    return check_and_notify(dry_run=dry_run)


if __name__ == "__main__":
    print("🔔 Утренняя сводка MAX…\n")
    result = send_notifications()
    print(f"✅ Отправлено сообщений:  {result['sent']}")
    print(f"⏭  Уже сегодня:           {result.get('skipped_already_today', 0)}")
    print(f"❌ Ошибок:                {result['errors']}")
