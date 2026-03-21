"""
Одноразовая миграция: таблица responsible_persons и заполнение ФИО из devices.
Запуск: python db/migrate_responsible.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db.database import get_connection, init_database  # noqa: E402


def main():
    init_database()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS responsible_persons (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            fio           TEXT NOT NULL UNIQUE,
            max_user_id   INTEGER
        )
        """
    )
    cur.execute(
        """
        INSERT OR IGNORE INTO responsible_persons (fio, max_user_id)
        SELECT DISTINCT TRIM(responsible_fio), NULL
        FROM devices
        WHERE TRIM(COALESCE(responsible_fio, '')) != ''
        """
    )
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM responsible_persons")
    n = cur.fetchone()[0]
    conn.close()
    print(f"✅ Таблица responsible_persons готова, записей: {n}")


if __name__ == "__main__":
    main()
