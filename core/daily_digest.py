"""
Утренняя сводная ведомость: стадии поверки, сроки, разрез по типам и ответственным.
Используется в MAX (notifier) и Email (email_notifier).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

STATUS_ORDER = ("red", "yellow", "green", "no_data")
STATUS_EMOJI = {
    "red": "🔴",
    "yellow": "🟡",
    "green": "🟢",
    "no_data": "⚪",
}
STATUS_TITLE = {
    "red": "Просрочено",
    "yellow": "Скоро срок (≤60 дн. до окончания)",
    "green": "В норме (>60 дн.)",
    "no_data": "Нет данных о сроке",
}


def _days_until(expiry_str: str | None) -> int | None:
    if not expiry_str:
        return None
    try:
        exp = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        return (exp - date.today()).days
    except Exception:
        return None


def compute_digest(devices: list[dict]) -> dict[str, Any]:
    """
    Счётчики по статусу (как в главной таблице), по срокам, по типу прибора, по ФИО.
    """
    by_status: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    by_type_status: dict[tuple[str, str], int] = defaultdict(int)
    by_fio: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "red": 0, "yellow": 0, "green": 0, "no_data": 0}
    )

    buckets = {
        "overdue": 0,
        "within_7": 0,
        "within_30": 0,
        "within_60": 0,
        "beyond_60": 0,
        "no_expiry": 0,
    }

    total = 0
    for d in devices:
        total += 1
        st = d.get("status") or "no_data"
        if st not in STATUS_ORDER:
            st = "no_data"
        by_status[st] += 1

        dtype = (d.get("type") or "—").strip() or "—"
        by_type[dtype] += 1
        by_type_status[(dtype, st)] += 1

        fio = (d.get("responsible_fio") or "").strip() or "— не указан —"
        by_fio[fio]["total"] += 1
        by_fio[fio][st] += 1

        exp = d.get("expiry_date")
        du = _days_until(exp)
        if du is None:
            buckets["no_expiry"] += 1
        elif du < 0:
            buckets["overdue"] += 1
        elif du <= 7:
            buckets["within_7"] += 1
        elif du <= 30:
            buckets["within_30"] += 1
        elif du <= 60:
            buckets["within_60"] += 1
        else:
            buckets["beyond_60"] += 1

    fio_rows = sorted(by_fio.items(), key=lambda x: x[0].lower())

    return {
        "total": total,
        "by_status": dict(by_status),
        "by_type": dict(by_type),
        "by_type_status": dict(by_type_status),
        "by_fio": fio_rows,
        "buckets": buckets,
        "date_str": date.today().strftime("%d.%m.%Y"),
    }


def format_digest_plain(digest: dict[str, Any], recipient_hint: str = "") -> str:
    """Текст для MAX / plain email."""
    lines: list[str] = []
    lines.append(f"📊 Утренняя сводка «Оркестратор Поверки» — {digest['date_str']}")
    if recipient_hint:
        lines.append(f"Получатель: {recipient_hint}")
    lines.append("")
    lines.append("━━━ По стадиям (как в журнале) ━━━")
    for st in STATUS_ORDER:
        n = digest["by_status"].get(st, 0)
        lines.append(f"{STATUS_EMOJI[st]} {STATUS_TITLE[st]}: {n}")
    lines.append(f"Всего приборов в журнале: {digest['total']}")
    lines.append("")
    lines.append("━━━ Статистика по срокам поверки ━━━")
    b = digest["buckets"]
    lines.append(f"• Просрочено: {b['overdue']}")
    lines.append(f"• Осталось до 7 дней: {b['within_7']}")
    lines.append(f"• Осталось 8–30 дней: {b['within_30']}")
    lines.append(f"• Осталось 31–60 дней: {b['within_60']}")
    lines.append(f"• Более 60 дней: {b['beyond_60']}")
    lines.append(f"• Нет даты окончания: {b['no_expiry']}")
    lines.append("")
    lines.append("━━━ По типам приборов ━━━")
    for t, n in sorted(digest["by_type"].items(), key=lambda x: -x[1]):
        lines.append(f"• {t}: {n} шт.")
    lines.append("")
    lines.append("━━━ По ответственным (всего / 🔴 / 🟡 / 🟢 / ⚪) ━━━")
    for fio, c in digest["by_fio"]:
        lines.append(
            f"• {fio}: {c['total']} "
            f"({STATUS_EMOJI['red']}{c['red']} "
            f"{STATUS_EMOJI['yellow']}{c['yellow']} "
            f"{STATUS_EMOJI['green']}{c['green']} "
            f"{STATUS_EMOJI['no_data']}{c['no_data']})"
        )
    lines.append("")
    lines.append("Подробный список приборов — в приложении. Это автоматическое сообщение.")
    return "\n".join(lines)


def format_digest_html(digest: dict[str, Any]) -> str:
    """HTML для письма."""
    rows_status = "".join(
        f"<tr><td style='padding:6px;'>{STATUS_EMOJI[st]} {STATUS_TITLE[st]}</td>"
        f"<td style='padding:6px;text-align:right;font-weight:bold;'>{digest['by_status'].get(st, 0)}</td></tr>"
        for st in STATUS_ORDER
    )
    b = digest["buckets"]
    rows_buckets = (
        f"<tr><td>Просрочено</td><td style='text-align:right'><b>{b['overdue']}</b></td></tr>"
        f"<tr><td>До 7 дней</td><td style='text-align:right'><b>{b['within_7']}</b></td></tr>"
        f"<tr><td>8–30 дней</td><td style='text-align:right'><b>{b['within_30']}</b></td></tr>"
        f"<tr><td>31–60 дней</td><td style='text-align:right'><b>{b['within_60']}</b></td></tr>"
        f"<tr><td>Более 60 дней</td><td style='text-align:right'><b>{b['beyond_60']}</b></td></tr>"
        f"<tr><td>Нет даты</td><td style='text-align:right'><b>{b['no_expiry']}</b></td></tr>"
    )
    types_html = "".join(
        f"<tr><td style='padding:4px 8px;'>{t}</td><td style='text-align:right'><b>{n}</b></td></tr>"
        for t, n in sorted(digest["by_type"].items(), key=lambda x: -x[1])
    )
    fio_html = "".join(
        f"<tr><td style='padding:4px 8px;'>{fio}</td>"
        f"<td style='text-align:right'>{c['total']}</td>"
        f"<td style='text-align:center'>{c['red']}</td>"
        f"<td style='text-align:center'>{c['yellow']}</td>"
        f"<td style='text-align:center'>{c['green']}</td>"
        f"<td style='text-align:center'>{c['no_data']}</td></tr>"
        for fio, c in digest["by_fio"]
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;font-size:14px;color:#333;">
<div style="max-width:720px;margin:0 auto;padding:16px;">
  <div style="background:#2c3e50;color:#fff;padding:14px 18px;border-radius:6px 6px 0 0;">
    <h2 style="margin:0;">📊 Утренняя сводка</h2>
    <p style="margin:6px 0 0;font-size:12px;opacity:.9;">Оркестратор Поверки · {digest["date_str"]}</p>
  </div>
  <div style="border:1px solid #dee2e6;border-top:0;padding:16px;background:#f8f9fa;">
    <h3 style="margin-top:0;">По стадиям</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">{rows_status}
      <tr style="background:#e9ecef;font-weight:bold;"><td style="padding:6px;">Всего</td>
      <td style="padding:6px;text-align:right;">{digest["total"]}</td></tr>
    </table>
    <h3>По срокам поверки</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">{rows_buckets}</table>
    <h3>По типам</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">{types_html}</table>
    <h3>По ответственным</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <tr style="background:#495057;color:#fff;">
        <th style="padding:6px;text-align:left;">ФИО</th>
        <th style="padding:6px;">Всего</th>
        <th style="padding:6px;">🔴</th><th style="padding:6px;">🟡</th>
        <th style="padding:6px;">🟢</th><th style="padding:6px;">⚪</th>
      </tr>
      {fio_html}
    </table>
    <p style="margin-top:16px;font-size:12px;color:#666;">Детали — в приложении. Письмо сформировано автоматически.</p>
  </div>
</div>
</body></html>"""


def digest_subject(digest: dict[str, Any]) -> str:
    r = digest["by_status"].get("red", 0)
    y = digest["by_status"].get("yellow", 0)
    if r:
        return f"⚠️ Сводка поверок: {digest['total']} приб., просрочено {r}"
    if y:
        return f"📋 Сводка поверок: {digest['total']} приб., скоро срок {y}"
    return f"📋 Сводка поверок: {digest['total']} приборов — {digest['date_str']}"
