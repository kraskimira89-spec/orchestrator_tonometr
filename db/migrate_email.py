import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_connection


def migrate():
    conn = get_connection()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(responsible_persons)").fetchall()]
    if "email" not in cols:
        conn.execute("ALTER TABLE responsible_persons ADD COLUMN email TEXT")
        print("Добавлено поле email в responsible_persons.")
    else:
        print("Поле email уже есть.")
    conn.commit()
    conn.close()
    print("Миграция email выполнена.")


if __name__ == "__main__":
    migrate()
