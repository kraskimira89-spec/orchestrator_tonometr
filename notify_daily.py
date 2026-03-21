"""
Ежедневный запуск уведомлений (планировщик Windows Task Scheduler).
Запуск: python notify_daily.py
Лог: logs/notify.log
"""
import logging
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "notify.log")


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main():
    _setup_logging()
    logging.info("notify_daily start")
    try:
        from core.notifier import send_notifications

        result = send_notifications()
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
