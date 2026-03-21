"""
CalDAV-синхронизация поверок с Яндекс.Календарём и Mail.ru Календарём.
Напоминания: за 60, 30, 7 и 2 дня до срока поверки.
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

REMIND_DAYS = [60, 30, 7, 2]


def get_caldav_settings(provider: str = "") -> dict:
    prefix = f"{provider}_" if provider else ""
    return {
        "url": get_setting(f"{prefix}caldav_url"),
        "username": get_setting(f"{prefix}caldav_username"),
        "password": get_setting(f"{prefix}caldav_password"),
        "calendar": get_setting(f"{prefix}caldav_calendar", ""),
    }


def connect_caldav(provider: str = "") -> caldav.Calendar:
    s = get_caldav_settings(provider)
    if not s["url"] or not s["username"] or not s["password"]:
        raise ValueError("CalDAV не настроен. Нажмите кнопку авторизации в правой панели.")
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
        for cal in calendars:
            if (getattr(cal, "name", "") or "").lower() == s["calendar"].lower():
                return cal
        raise RuntimeError(
            f"Календарь «{s['calendar']}» не найден. "
            f"Доступны: {[getattr(c, 'name', '?') for c in calendars]}"
        )
    return calendars[0]


def _find_event_by_uid(cal: caldav.Calendar, uid: str):
    by_uid = getattr(cal, "event_by_uid", None)
    if callable(by_uid):
        try:
            return by_uid(uid)
        except Exception:
            pass
    try:
        for event in cal.events():
            data = getattr(event, "data", "") or ""
            if f"UID:{uid}" in data:
                return event
    except Exception:
        pass
    return None


def _save_event(cal: caldav.Calendar, vcal: str):
    save_event = getattr(cal, "save_event", None)
    if callable(save_event):
        return save_event(vcal)
    add_event = getattr(cal, "add_event", None)
    if callable(add_event):
        return add_event(vcal)
    raise RuntimeError("Календарь не поддерживает save_event/add_event")


def _ical_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _alarm_block(days_before: int, summary: str) -> str:
    labels = {60: "2 месяца", 30: "месяц", 7: "неделя", 2: "2 дня"}
    label = labels.get(days_before, f"{days_before} дней")
    return (
        "BEGIN:VALARM\r\n"
        f"TRIGGER:-P{days_before}D\r\n"
        "ACTION:DISPLAY\r\n"
        f"DESCRIPTION:{_ical_escape(f'До поверки {label}: {summary}')}\r\n"
        "END:VALARM"
    )


def _make_vcal(uid: str, device: dict, expiry_date: str) -> str:
    exp = date.fromisoformat(expiry_date)
    dtype = device.get("type") or device.get("device_type") or ""
    inv = device.get("inventory_number") or ""
    location = device.get("location") or ""
    resp = device.get("responsible_fio") or ""

    summary = f"Поверка: {dtype} {inv}".strip()
    desc = (
        f"Местонахождение: {location}\n"
        f"Ответственный: {resp}\n"
        f"Срок поверки: {expiry_date}"
    )
    alarms = "\r\n".join(_alarm_block(d, summary) for d in REMIND_DAYS)

    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//OrchestratorTonometr//RU\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"SUMMARY:{_ical_escape(summary)}\r\n"
        f"DESCRIPTION:{_ical_escape(desc)}\r\n"
        f"DTSTART;VALUE=DATE:{exp.strftime('%Y%m%d')}\r\n"
        f"DTEND;VALUE=DATE:{(exp + timedelta(days=1)).strftime('%Y%m%d')}\r\n"
        f"{alarms}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def sync_device(device: dict, expiry_date: str, provider: str = "") -> str:
    cal = connect_caldav(provider)
    existing_uid = device.get("calendar_event_id")
    if existing_uid:
        try:
            event = _find_event_by_uid(cal, existing_uid)
            if event:
                event.data = _make_vcal(existing_uid, device, expiry_date)
                event.save()
                return existing_uid
        except Exception:
            pass

    uid = str(uuid.uuid4())
    _save_event(cal, _make_vcal(uid, device, expiry_date))
    set_device_calendar_event_id(int(device["id"]), uid)
    return uid


def delete_device_event(device: dict, provider: str = ""):
    uid = device.get("calendar_event_id")
    if not uid:
        return
    try:
        cal = connect_caldav(provider)
        event = _find_event_by_uid(cal, uid)
        if event:
            event.delete()
    except Exception as e:
        print(f"CalDAV delete error: {e}")


def sync_all_devices(provider: str = "", progress_callback=None) -> dict:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT d.id, d.type, d.inventory_number, d.location,
               d.responsible_fio, d.calendar_event_id, d.is_active,
               v.expiry_date
        FROM devices d
        LEFT JOIN verifications v ON v.id = (
            SELECT id FROM verifications
            WHERE device_id = d.id
            ORDER BY expiry_date DESC LIMIT 1
        )
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
            sync_device(device, expiry, provider=provider)
            synced += 1
        except Exception as e:
            print(f"Ошибка {device.get('inventory_number')}: {e}")
            errors += 1

    return {"synced": synced, "skipped": skipped, "errors": errors}


def test_connection(provider: str = "") -> str:
    try:
        cal = connect_caldav(provider)
        cal_name = getattr(cal, "name", None) or getattr(cal, "displayname", None) or "?"
        return f"✅ Подключено. Календарь: «{cal_name}»"
    except Exception as e:
        return f"❌ Ошибка: {e}"
