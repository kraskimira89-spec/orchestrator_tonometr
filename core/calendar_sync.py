"""
CalDAV-синхронизация поверок.
Напоминания: за 60, 30, 7 и 2 дня до срока поверки.
Поддержка двух провайдеров одновременно: yandex и mailru.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from datetime import date, timedelta
from typing import Any

from db.database import (
    get_connection,
    get_setting,
    set_device_calendar_event_id,
)

REMIND_DAYS = [60, 30, 7, 2]

REMIND_LABELS = {
    60: "2 месяца",
    30: "1 месяц",
    7: "1 неделя",
    2: "2 дня",
}

_CALDAV_MOD = None


def _get_caldav():
    """Ленивый импорт: приложение стартует без pip install caldav."""
    global _CALDAV_MOD
    if _CALDAV_MOD is not None:
        return _CALDAV_MOD
    try:
        import caldav as m

        _CALDAV_MOD = m
        return m
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "Не установлен пакет «caldav». Выполните: python -m pip install caldav"
        ) from e


def get_caldav_settings(provider: str) -> dict:
    p = provider
    return {
        "url": get_setting(f"{p}_caldav_url"),
        "username": get_setting(f"{p}_caldav_username"),
        "password": get_setting(f"{p}_caldav_password"),
        "calendar": get_setting(f"{p}_caldav_calendar", ""),
    }


def connect_caldav(provider: str) -> Any:
    caldav = _get_caldav()
    s = get_caldav_settings(provider)
    if not s["url"] or not s["username"] or not s["password"]:
        raise ValueError(
            f"CalDAV ({provider}) не настроен. "
            "Нажмите кнопку авторизации в правой панели."
        )
    client = caldav.DAVClient(
        url=s["url"],
        username=s["username"],
        password=s["password"],
    )
    principal = client.principal()
    calendars = principal.calendars()
    if not calendars:
        raise RuntimeError("Календари не найдены на сервере.")
    cal_name = s["calendar"]
    if cal_name:
        for cal in calendars:
            if (getattr(cal, "name", "") or "").lower() == cal_name.lower():
                return cal
        raise RuntimeError(
            f"Календарь «{cal_name}» не найден. "
            f"Доступны: {[getattr(c, 'name', '?') for c in calendars]}"
        )
    return calendars[0]


def _ical_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _find_event_by_uid(cal: Any, uid: str):
    fn = getattr(cal, "event_by_uid", None)
    if callable(fn):
        try:
            return fn(uid)
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


def _search_event_by_uid(cal: Any, uid: str):
    search = getattr(cal, "search", None)
    if callable(search):
        try:
            results = search(uid=uid)
            if results:
                return results[0]
        except (TypeError, Exception):
            pass
    return _find_event_by_uid(cal, uid)


def _alarm_block(days: int, summary: str) -> str:
    label = REMIND_LABELS.get(days, f"{days} дней")
    desc = _ical_escape(f"До поверки {label}: {summary}")
    return (
        f"BEGIN:VALARM\n"
        f"TRIGGER:-P{days}D\n"
        f"ACTION:DISPLAY\n"
        f"DESCRIPTION:{desc}\n"
        f"END:VALARM"
    )


def _make_vcal(uid: str, device: dict, expiry_date: str) -> str:
    exp = date.fromisoformat(expiry_date)
    dtype = device.get("device_type") or device.get("type", "")
    inv = device.get("inventory_number", "")
    location = device.get("location", "")
    resp = device.get("responsible_fio", "")

    summary = f"Поверка: {dtype} {inv}"
    desc = (
        f"Местонахождение: {location}\n"
        f"Ответственный: {resp}\n"
        f"Срок поверки: {expiry_date}"
    )

    def dt(d: date) -> str:
        return d.strftime("%Y%m%d")

    alarms = "\n".join(_alarm_block(d, summary) for d in REMIND_DAYS)

    return (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//PoverkiVSE//RU\n"
        "BEGIN:VEVENT\n"
        f"UID:{uid}\n"
        f"SUMMARY:{_ical_escape(summary)}\n"
        f"DESCRIPTION:{_ical_escape(desc)}\n"
        f"DTSTART;VALUE=DATE:{dt(exp)}\n"
        f"DTEND;VALUE=DATE:{dt(exp + timedelta(days=1))}\n"
        f"{alarms}\n"
        "END:VEVENT\n"
        "END:VCALENDAR"
    )


def _add_event(cal: Any, vcal: str):
    add = getattr(cal, "add_event", None)
    if callable(add):
        return add(vcal)
    save = getattr(cal, "save_event", None)
    if callable(save):
        return save(vcal)
    raise RuntimeError("Календарь не поддерживает add_event/save_event")


def sync_device(device: dict, expiry_date: str, provider: str) -> str:
    """Создаёт или обновляет событие в CalDAV. Возвращает UID."""
    cal = connect_caldav(provider)
    existing_uid = device.get("calendar_event_id")

    if existing_uid:
        try:
            event = _search_event_by_uid(cal, existing_uid)
            if event:
                event.data = _make_vcal(existing_uid, device, expiry_date)
                event.save()
                return existing_uid
        except Exception:
            pass

    uid = str(uuid.uuid4())
    vcal = _make_vcal(uid, device, expiry_date)
    _add_event(cal, vcal)
    set_device_calendar_event_id(int(device["id"]), uid)
    return uid


def delete_device_event(device: dict, provider: str):
    uid = device.get("calendar_event_id")
    if not uid:
        return
    try:
        cal = connect_caldav(provider)
        event = _search_event_by_uid(cal, uid)
        if event:
            event.delete()
    except Exception as e:
        print(f"CalDAV delete error ({provider}): {e}")


def sync_all_devices(provider: str, progress_callback=None) -> dict:
    """Синхронизирует все приборы с актуальными датами поверки."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT d.id, d.type, d.inventory_number, d.location,
               d.responsible_fio, d.calendar_event_id,
               v.expiry_date
        FROM devices d
        LEFT JOIN verifications v ON v.id = (
            SELECT id FROM verifications
            WHERE device_id = d.id
            ORDER BY expiry_date DESC LIMIT 1
        )
        """
    ).fetchall()
    conn.close()

    total = len(rows)
    synced = skipped = errors = 0

    for i, row in enumerate(rows):
        if progress_callback:
            progress_callback(i + 1, total)
        device = dict(row)
        expiry = device.get("expiry_date")
        if not expiry:
            skipped += 1
            continue
        try:
            sync_device(device, expiry, provider)
            synced += 1
        except Exception as e:
            print(f"Ошибка CalDAV {device.get('inventory_number')}: {e}")
            errors += 1

    return {"synced": synced, "skipped": skipped, "errors": errors}


def test_connection(provider: str) -> str:
    try:
        cal = connect_caldav(provider)
        name = getattr(cal, "name", None) or getattr(cal, "displayname", None) or "?"
        return f"✅ Подключено. Календарь: «{name}»"
    except Exception as e:
        return f"❌ Ошибка: {e}"


def auto_sync_device(device: dict, expiry_date: str):
    """
    Вызывается автоматически после сохранения поверки.
    В БД хранится один UID события — синхронизируем с первым доступным
    провайдером (yandex, затем mail.ru). Полная синхронизация обоих — из диалога.
    Ошибки не бросает — только пишет в консоль.
    """
    for provider in ("yandex", "mailru"):
        if not get_setting(f"{provider}_caldav_url"):
            continue
        try:
            uid = sync_device(device, expiry_date, provider)
            device["calendar_event_id"] = uid
            print(f"CalDAV auto-sync OK ({provider}): {device.get('inventory_number')}")
            return
        except Exception as e:
            print(f"CalDAV auto-sync error ({provider}): {e}")
