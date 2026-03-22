"""
Email: утренняя сводная ведомость (одно письмо на smtp_admin_email в день).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date

from core.digest_workbook import build_digest_xlsx
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


def send_email(
    to_addr: str,
    subject: str,
    html: str,
    plain: str,
    attachment: tuple[bytes, str] | None = None,
) -> bool:
    s = get_smtp_settings()
    if not s["host"] or not s["login"] or not s["password"]:
        print("SMTP не настроен — письмо не отправлено.")
        return False

    from_addr = s["from"] or s["login"]

    msg_root = MIMEMultipart("mixed")
    msg_root["Subject"] = subject
    msg_root["From"] = from_addr
    msg_root["To"] = to_addr

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain, "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg_root.attach(alt)

    if attachment:
        data, filename = attachment
        part = MIMEBase(
            "application",
            "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=filename,
        )
        msg_root.attach(part)

    try:
        if s["ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(s["host"], s["port"], context=context) as server:
                server.login(s["login"], s["password"])
                server.sendmail(from_addr, to_addr, msg_root.as_string())
        else:
            with smtplib.SMTP(s["host"], s["port"]) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.login(s["login"], s["password"])
                server.sendmail(from_addr, to_addr, msg_root.as_string())
        print(f"  Email → {to_addr}: OK")
        return True
    except Exception as e:
        print(f"  Email → {to_addr}: ОШИБКА {e}")
        return False


def test_smtp(to_addr: str) -> str:
    digest = compute_digest([])
    plain = (
        "Тест SMTP — PoverkiVSE.\n\n"
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
    xlsx = build_digest_xlsx(digest, [])
    fn = f"test_poverki_svodka_{date.today().isoformat()}.xlsx"
    ok = send_email(
        to_addr,
        "✅ Тест SMTP — PoverkiVSE",
        html,
        plain,
        attachment=(xlsx, fn),
    )
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

    devices = get_all_devices()
    digest = compute_digest(devices)
    subject = digest_subject(digest)
    html = format_digest_html(digest)
    plain = format_digest_plain(digest)
    plain += (
        "\n\nВо вложении файл Excel (.xlsx): сводка, по ответственным, полный список приборов."
    )
    html += (
        "<p style='font-size:12px;color:#666;'>"
        "<b>Вложение:</b> Excel (.xlsx) — листы «Сводка», «По ответственным», «Приборы»."
        "</p>"
    )

    if dry_run:
        print(f"  [dry-run] сводка + xlsx → {admin} ({digest['total']} приборов в журнале)")
        return {
            "sent": 1,
            "skipped": 0,
            "errors": 0,
            "skipped_already_today": 0,
        }

    xlsx = build_digest_xlsx(digest, devices)
    fn = f"Poverki_svodka_{date.today().isoformat()}.xlsx"

    if send_email(admin, subject, html, plain, attachment=(xlsx, fn)):
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
