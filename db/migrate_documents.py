import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_connection  # noqa: E402


def migrate():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS device_documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            filename    TEXT NOT NULL,
            filepath    TEXT NOT NULL,
            uploaded_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    print("Миграция device_documents выполнена.")


if __name__ == "__main__":
    migrate()
