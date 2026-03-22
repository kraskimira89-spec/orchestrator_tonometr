"""
Email: утренняя сводная ведомость (одно письмо на smtp_admin_email в день).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date

from core.daily_digest import (
    compute_digest,
    digest_subject,
    format_digest_html,
    format_digest_plain,
)
from db.database import (
    get_all_devices,
    get_setting,
    log_digest_notification,
    was_digest_notification_sent_today,
)

ADMIN_EMAIL_KEY = "smtp_admin_email"

SMTP_PRESETS = {
    "Mail.ru": {
        "host": "smtp.mail.ru",
        "port": 465,
        "ssl": True,
    },
    "Яндекс": {
        "host": "smtp.yandex.ru",
        "port": 465,
        "ssl": True,
    },
    "Gmail": {
        "host": "smtp.gmail.com",
        "port": 587,
        "ssl": False,
    },
    "Другой": {
        "host": "",
        "port": 587,
        "ssl": False,
    },
}


def get_smtp_settings() -> dict:
    return {
        "host": get_setting("smtp_host"),
        "port": int(get_setting("smtp_port", "465") or "465"),
        "ssl": get_setting("smtp_ssl", "1") == "1",
        "login": get_setting("smtp_login"),
        "password": get_setting("smtp_password"),
        "from": get_setting("smtp_from"),
        "admin": get_setting(ADMIN_EMAIL_KEY),
    }


def send_email(to_addr: str, subject: str, html: str, plain: str) -> bool:
    s = get_smtp_settings()
    if not s["host"] or not s["login"] or not s["password"]:
        print("SMTP не настроен — письмо не отправлено.")
        return False

    from_addr = s["from"] or s["login"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if s["ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(s["host"], s["port"], context=context) as server:
                server.login(s["login"], s["password"])
                server.sendmail(from_addr, to_addr, msg.as_string())
        else:
            with smtplib.SMTP(s["host"], s["port"]) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.login(s["login"], s["password"])
                server.sendmail(from_addr, to_addr, msg.as_string())
        print(f"  Email → {to_addr}: OK")
        return True
    except Exception as e:
        print(f"  Email → {to_addr}: ОШИБКА {e}")
        return False


def test_smtp(to_addr: str) -> str:
    digest = compute_digest([])
    plain = (
        "Тест SMTP — Оркестратор Поверки.\n\n"
        + format_digest_plain(digest).replace(
            "Подробный список приборов — в приложении.",
            "Если вы читаете это письмо, SMTP настроен верно.",
        )
    )
    html = format_digest_html(digest).replace(
        "Детали — в приложении. Письмо сформировано автоматически.",
        "<b>Тест SMTP.</b> Если письмо получено — настройки верны.<br>"
        "Детали — в приложении.",
    )
    ok = send_email(to_addr, "✅ Тест SMTP — Оркестратор Поверки", html, plain)
    return "✅ Письмо отправлено успешно." if ok else "❌ Ошибка отправки. Проверьте настройки SMTP."


def send_email_notifications(dry_run: bool = False) -> dict:
    """
    Одна сводка на email администратора за сутки (без перечня приборов).
    """
    s = get_smtp_settings()
    admin = (s.get("admin") or "").strip()
    if not admin:
        print("Email: не задан «Email администратора» в настройках SMTP — сводку некуда отправить.")
        return {
            "sent": 0,
            "skipped": 1,
            "errors": 0,
            "skipped_already_today": 0,
        }

    marker = "email_digest_admin"
    if was_digest_notification_sent_today("email_digest", marker):
        print("Email: утренняя сводка уже отправлялась сегодня.")
        return {
            "sent": 0,
            "skipped": 0,
            "errors": 0,
            "skipped_already_today": 1,
        }

    digest = compute_digest(get_all_devices())
    subject = digest_subject(digest)
    html = format_digest_html(digest)
    plain = format_digest_plain(digest)

    if dry_run:
        print(f"  [dry-run] сводка → {admin} ({digest['total']} приборов в журнале)")
        return {
            "sent": 1,
            "skipped": 0,
            "errors": 0,
            "skipped_already_today": 0,
        }

    if send_email(admin, subject, html, plain):
        log_digest_notification("email_digest", marker)
        return {
            "sent": 1,
            "skipped": 0,
            "errors": 0,
            "skipped_already_today": 0,
        }

    return {
        "sent": 0,
        "skipped": 0,
        "errors": 1,
        "skipped_already_today": 0,
    }
