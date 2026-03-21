import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from db.database import get_connection, init_database  # noqa: E402


def reset_db():
    init_database()
    conn = get_connection()
    cur = conn.cursor()
    # очищаем только рабочие данные, пользователей-админа оставляем
    cur.execute("DELETE FROM notification_log")
    cur.execute("DELETE FROM verifications")
    cur.execute("DELETE FROM devices")
    conn.commit()
    conn.close()
    print("База очищена (devices, verifications, notification_log).")


if __name__ == "__main__":
    reset_db()
