"""Даты напоминаний как в журнале Excel: −2 мес., −1 мес., −7 дн., −2 дн. до окончания поверки."""
from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta


def journal_reminder_dates(expiry_str: str | None) -> tuple[str, str, str, str]:
    """Четыре строки YYYY-MM-DD или пустые, если срока нет."""
    if not expiry_str or not str(expiry_str).strip():
        return ("", "", "", "")
    raw = str(expiry_str).strip()[:10]
    try:
        exp = date.fromisoformat(raw)
    except ValueError:
        return ("", "", "", "")
    d2m = exp - relativedelta(months=2)
    d1m = exp - relativedelta(months=1)
    d7 = exp - timedelta(days=7)
    d2 = exp - timedelta(days=2)
    return (d2m.isoformat(), d1m.isoformat(), d7.isoformat(), d2.isoformat())
