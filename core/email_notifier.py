"""
Email-уведомления о поверках через SMTP.
Полностью независим от CalDAV и MAX.
Поддерживает Mail.ru, Яндекс, Gmail и любой SMTP.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, timedelta

from db.database import get_connection, get_setting, get_responsible_email

WARN_DAYS = 30
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


def _device_type_label(d: dict) -> str:
    return d.get("device_type") or d.get("type") or ""


def _make_subject(count: int, has_overdue: bool) -> str:
    if has_overdue:
        return f"⚠️ Поверки: {count} приборов требуют внимания (есть просроченные)"
    return f"📋 Поверки: {count} приборов — срок истекает в ближайшие 30 дней"


def _make_html(fio: str, devices: list, today: date) -> str:
    rows_html = ""
    for d in devices:
        expiry = d["expiry_date"]
        exp_date = date.fromisoformat(expiry)
        days_left = (exp_date - today).days

        if days_left < 0:
            status_txt = f"ПРОСРОЧЕНО на {abs(days_left)} дн."
            status_color = "#c0392b"
            row_bg = "#fdf2f2"
        elif days_left <= 7:
            status_txt = f"через {days_left} дн. ⚠️"
            status_color = "#e67e22"
            row_bg = "#fef9f0"
        else:
            status_txt = f"через {days_left} дн."
            status_color = "#27ae60"
            row_bg = "#f9fef9"

        rows_html += f"""
        <tr style="background:{row_bg};">
          <td style="padding:6px 10px; border-bottom:1px solid #eee;">
            {_device_type_label(d)}
          </td>
          <td style="padding:6px 10px; border-bottom:1px solid #eee;">
            {d.get('inventory_number','')}
          </td>
          <td style="padding:6px 10px; border-bottom:1px solid #eee;">
            {d.get('location','')}
          </td>
          <td style="padding:6px 10px; border-bottom:1px solid #eee;">
            {expiry}
          </td>
          <td style="padding:6px 10px; border-bottom:1px solid #eee;
                     color:{status_color}; font-weight:bold;">
            {status_txt}
          </td>
        </tr>"""

    name_line = f"Уважаемый(ая) <b>{fio}</b>," if fio else "Добрый день,"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
  <div style="max-width:700px; margin:0 auto; padding:20px;">

    <div style="background:#2c3e50; color:white; padding:16px 20px;
                border-radius:6px 6px 0 0;">
      <h2 style="margin:0;">📋 Оркестратор Поверки</h2>
      <p style="margin:4px 0 0; font-size:12px; opacity:0.8;">
        Автоматическое уведомление о сроках поверки
      </p>
    </div>

    <div style="background:#f8f9fa; padding:16px 20px; border:1px solid #dee2e6;
                border-top:none; border-radius:0 0 6px 6px;">

      <p>{name_line}</p>
      <p>Следующие приборы требуют вашего внимания:</p>

      <table style="width:100%; border-collapse:collapse;
                    border:1px solid #dee2e6; border-radius:4px;">
        <thead>
          <tr style="background:#495057; color:white;">
            <th style="padding:8px 10px; text-align:left;">Тип</th>
            <th style="padding:8px 10px; text-align:left;">Инв. №</th>
            <th style="padding:8px 10px; text-align:left;">Местонахождение</th>
            <th style="padding:8px 10px; text-align:left;">Срок поверки</th>
            <th style="padding:8px 10px; text-align:left;">Статус</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>

      <p style="margin-top:20px; font-size:12px; color:#666;">
        Это письмо отправлено автоматически системой «Оркестратор Поверки».<br>
        Дата отправки: {today.strftime('%d.%m.%Y')}
      </p>
    </div>

  </div>
</body>
</html>"""


def _make_plain(fio: str, devices: list, today: date) -> str:
    lines = [
        "Оркестратор Поверки — уведомление о сроках",
        f"Дата: {today.strftime('%d.%m.%Y')}",
        "",
        f"Ответственный: {fio}" if fio else "Уважаемый коллега,",
        "",
        "Приборы требующие внимания:",
        "-" * 60,
    ]
    for d in devices:
        expiry = d["expiry_date"]
        exp_date = date.fromisoformat(expiry)
        days_left = (exp_date - today).days
        if days_left < 0:
            status = f"ПРОСРОЧЕНО на {abs(days_left)} дн."
        else:
            status = f"через {days_left} дн."
        lines.append(
            f"{_device_type_label(d)} | {d.get('inventory_number','')} | "
            f"{d.get('location','')} | {expiry} | {status}"
        )
    lines += ["", "Это письмо отправлено автоматически."]
    return "\n".join(lines)


def send_email(to_addr: str, subject: str, html: str, plain: str) -> bool:
    """Отправляет письмо. Возвращает True при успехе."""
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
    """Отправляет тестовое письмо. Возвращает строку результата."""
    today = date.today()
    html = _make_html("Тестовый получатель", [], today).replace(
        "Следующие приборы требуют вашего внимания:",
        "Это тестовое письмо из системы «Оркестратор Поверки».<br>"
        "Если вы его получили — SMTP настроен корректно.",
    )
    plain = "Тестовое письмо из системы Оркестратор Поверки. SMTP работает корректно."
    ok = send_email(to_addr, "✅ Тест SMTP — Оркестратор Поверки", html, plain)
    return "✅ Письмо отправлено успешно." if ok else "❌ Ошибка отправки. Проверьте настройки SMTP."


def send_email_notifications(dry_run: bool = False) -> dict:
    """
    Отправляет email каждому ответственному о его приборах.
    Fallback: если email не указан — шлёт на admin email.
    """
    today = date.today()
    deadline = today + timedelta(days=WARN_DAYS)

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT d.id, d.type, d.inventory_number, d.location,
               d.responsible_fio,
               v.expiry_date
        FROM devices d
        LEFT JOIN verifications v ON v.id = (
            SELECT id FROM verifications
            WHERE device_id = d.id
            ORDER BY expiry_date DESC LIMIT 1
        )
        WHERE v.expiry_date IS NOT NULL
          AND v.expiry_date <= ?
        """,
        (deadline.isoformat(),),
    ).fetchall()
    conn.close()

    if not rows:
        print("Email: нет приборов с истекающим сроком.")
        return {"sent": 0, "skipped": 0, "errors": 0}

    by_fio: dict[str, list] = {}
    for row in rows:
        r = dict(row)
        r["device_type"] = r.get("type") or ""
        fio = r["responsible_fio"] or ""
        by_fio.setdefault(fio, []).append(r)

    s = get_smtp_settings()
    admin_email = s["admin"]

    sent = skipped = errors = 0

    for fio, devices in by_fio.items():
        email = get_responsible_email(fio) or admin_email
        if not email:
            print(f"  Нет email для «{fio or 'без ответственного'}» — пропускаем.")
            skipped += 1
            continue

        has_overdue = any(date.fromisoformat(d["expiry_date"]) < today for d in devices)
        subject = _make_subject(len(devices), has_overdue)
        html = _make_html(fio, devices, today)
        plain = _make_plain(fio, devices, today)

        if dry_run:
            print(f"  [dry-run] {fio} → {email}: {len(devices)} приборов")
            sent += 1
            continue

        if send_email(email, subject, html, plain):
            sent += 1
        else:
            errors += 1

    return {"sent": sent, "skipped": skipped, "errors": errors}
