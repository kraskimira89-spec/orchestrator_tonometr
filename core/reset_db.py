import os
import shutil
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from db.database import DOCUMENTS_DIR, get_connection, init_database  # noqa: E402


def reset_db():
    """Удаляет все приборы, поверки, лог уведомлений и папки документов; настройки и users не трогает."""
    init_database()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM notification_log")
    cur.execute("DELETE FROM verifications")
    # device_documents удаляются каскадом при DELETE FROM devices
    cur.execute("DELETE FROM devices")
    conn.commit()
    conn.close()

    if os.path.isdir(DOCUMENTS_DIR):
        for name in os.listdir(DOCUMENTS_DIR):
            path = os.path.join(DOCUMENTS_DIR, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)

    print("База очищена (devices, verifications, notification_log, каталоги documents/).")


if __name__ == "__main__":
    reset_db()
