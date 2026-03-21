"""
Ежедневный запуск уведомлений (планировщик Windows Task Scheduler).
Запуск: python notify_daily.py
Проверка без отправки: python notify_daily.py --dry-run
Лог: logs/notify.log
"""
import argparse
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from datetime import datetime

log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
LOG_PATH = os.path.join(log_dir, "notify.log")


def _setup_logging():
    fmt = "%(asctime)s %(levelname)s %(message)s"
    # Явный UTF-8 в файл (читать: Get-Content ... -Encoding UTF8)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format=fmt,
        encoding="utf-8",
        force=True,
    )
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    _con = logging.StreamHandler(sys.stdout)
    _con.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(_con)


def main():
    parser = argparse.ArgumentParser(description="Ежедневные уведомления MAX")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Не отправлять сообщения, только вывести фрагменты в консоль",
    )
    args = parser.parse_args()

    _setup_logging()
    logging.info("notify_daily start %s", datetime.now().isoformat(timespec="seconds"))
    if args.dry_run:
        logging.info("режим --dry-run")
    try:
        from core.notifier import send_notifications

        result = send_notifications(dry_run=args.dry_run)
        logging.info(
            "notify_daily done: sent=%s skipped=%s errors=%s",
            result.get("sent"),
            result.get("skipped"),
            result.get("errors"),
        )
    except Exception:
        logging.exception("notify_daily failed")
        raise


if __name__ == "__main__":
    main()
