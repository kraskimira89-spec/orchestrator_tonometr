"""
Синхронизация событий поверки с CalDAV-календарём (Mail.ru, Яндекс и др.).

Стандартные CalDAV URL:
  Mail.ru:  https://caldav.mail.ru/calendars/<логин>@mail.ru/
  Яндекс:   https://caldav.yandex.ru/calendars/<логин>/
"""
import os
import sys
import uuid
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import caldav  # noqa: E402

from db.database import (  # noqa: E402
    get_connection,
    get_setting,
    set_device_calendar_event_id,
)


def get_caldav_settings() -> dict:
    return {
        "url": get_setting("caldav_url"),
        "username": get_setting("caldav_username"),
        "password": get_setting("caldav_password"),
        "calendar": get_setting("caldav_calendar", ""),
    }


def connect_caldav() -> caldav.Calendar:
    """Возвращает объект Calendar. Бросает исключение если не удаётся подключиться."""
    s = get_caldav_settings()
    if not s["url"] or not s["username"] or not s["password"]:
        raise ValueError("CalDAV не настроен. Откройте «Синхр. календарь» и заполните поля.")

    client = caldav.DAVClient(
        url=s["url"],
        username=s["username"],
        password=s["password"],
    )
    principal = client.principal()
    calendars = principal.calendars()

    if not calendars:
        raise RuntimeError("Календари не найдены на сервере.")

    if s["calendar"]:
        want = s["calendar"].strip().lower()
        for cal in calendars:
            cal_name = (cal.name or "") if hasattr(cal, "name") else ""
            if str(cal_name).lower() == want:
                return cal
        names = [getattr(c, "name", "") or "?" for c in calendars]
        raise RuntimeError(f"Календарь «{s['calendar']}» не найден. Доступны: {names}")

    return calendars[0]


def _find_event_by_uid(cal: caldav.Calendar, uid: str):
    fn = getattr(cal, "event_by_uid", None)
    if callable(fn):
        try:
            return fn(uid)
        except Exception:
            pass
    try:
        for ev in cal.events():
            try:
                if uid in (ev.data or ""):
                    return ev
            except Exception:
                continue
    except Exception:
        pass
    return None


def _save_ics(cal: caldav.Calendar, ics: str):
    fn = getattr(cal, "save_event", None)
    if callable(fn):
        return fn(ics)
    fn = getattr(cal, "add_event", None)
    if callable(fn):
        return fn(ics)
    raise RuntimeError("Календарь не поддерживает save_event/add_event")


def _ical_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _make_vcal(uid: str, device: dict, expiry_date: str) -> str:
    """Формирует iCalendar-текст для события поверки (все дневное событие)."""
    exp = date.fromisoformat(expiry_date)
    dtype = device.get("type") or device.get("device_type") or ""
    inv = device.get("inventory_number") or ""
    location = device.get("location") or ""
    resp = device.get("responsible_fio") or ""

    summary = _ical_escape(f"Поверка: {dtype} {inv}".strip())
    desc = _ical_escape(
        f"Местонахождение: {location}\nОтветственный: {resp}\nСрок поверки: {expiry_date}"
    )

    def dt(d: date) -> str:
        return d.strftime("%Y%m%d")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OrchestratorTonometr//RU",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{desc}",
        f"DTSTART;VALUE=DATE:{dt(exp)}",
        f"DTEND;VALUE=DATE:{dt(exp + timedelta(days=1))}",
        "BEGIN:VALARM",
        "TRIGGER:-P30D",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_ical_escape('Поверка через 30 дней: ' + (dtype + ' ' + inv).strip())}",
        "END:VALARM",
        "BEGIN:VALARM",
        "TRIGGER:-P7D",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_ical_escape('Поверка через 7 дней: ' + (dtype + ' ' + inv).strip())}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def _calendar_name(cal: caldav.Calendar) -> str:
    return str(getattr(cal, "name", None) or getattr(cal, "displayname", None) or "календарь")


def sync_device(device: dict, expiry_date: str) -> str:
    """
    Создаёт или обновляет событие в CalDAV для прибора.
    Возвращает UID события.
    """
    cal = connect_caldav()
    existing_uid = device.get("calendar_event_id")
    dev_id = int(device["id"])

    if existing_uid:
        try:
            ev = _find_event_by_uid(cal, existing_uid)
            if ev is not None:
                new_vcal = _make_vcal(existing_uid, device, expiry_date)
                ev.data = new_vcal
                ev.save()
                return existing_uid
        except Exception:
            pass

    new_uid = str(uuid.uuid4())
    vcal = _make_vcal(new_uid, device, expiry_date)
    _save_ics(cal, vcal)
    set_device_calendar_event_id(dev_id, new_uid)
    return new_uid


def delete_device_event(device: dict) -> None:
    """Удаляет событие из CalDAV если оно есть."""
    uid = device.get("calendar_event_id")
    if not uid:
        return
    try:
        cal = connect_caldav()
        ev = _find_event_by_uid(cal, uid)
        if ev is not None:
            ev.delete()
    except Exception as e:
        print(f"Не удалось удалить событие CalDAV: {e}")


def sync_all_devices(progress_callback=None) -> dict:
    """
    Синхронизирует активные приборы с последней датой окончания поверки.
    progress_callback(current, total) — опционально.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT d.id, d.type, d.inventory_number, d.location,
               d.responsible_fio, d.calendar_event_id,
               v.expiry_date, d.is_active
        FROM devices d
        LEFT JOIN (
            SELECT device_id, MAX(expiry_date) AS expiry_date
            FROM verifications
            GROUP BY device_id
        ) v ON d.id = v.device_id
        WHERE (d.is_active IS NULL OR d.is_active = 1)
        """
    ).fetchall()
    conn.close()

    total = len(rows)
    synced = 0
    skipped = 0
    errors = 0

    for i, row in enumerate(rows):
        if progress_callback:
            progress_callback(i + 1, total)

        device = dict(row)
        expiry = device.get("expiry_date")
        if not expiry:
            skipped += 1
            continue

        try:
            sync_device(device, expiry)
            synced += 1
        except Exception as e:
            print(f"Ошибка синхронизации {device.get('inventory_number')}: {e}")
            errors += 1

    return {"synced": synced, "skipped": skipped, "errors": errors}


def test_connection() -> str:
    """Проверяет подключение. Возвращает строку с результатом."""
    try:
        cal = connect_caldav()
        return f"✅ Подключено. Календарь: «{_calendar_name(cal)}»"
    except Exception as e:
        return f"❌ Ошибка: {e}"
