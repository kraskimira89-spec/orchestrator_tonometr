import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_connection  # noqa: E402


def migrate():
    conn = get_connection()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(devices)").fetchall()]
    if "calendar_event_id" not in cols:
        conn.execute("ALTER TABLE devices ADD COLUMN calendar_event_id TEXT")
        print("Добавлено поле calendar_event_id в devices.")
    else:
        print("Поле calendar_event_id уже существует.")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    conn.close()
    print("Миграция caldav выполнена.")


if __name__ == "__main__":
    migrate()
