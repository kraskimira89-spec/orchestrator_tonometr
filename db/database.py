import os
import shutil
import sqlite3
from datetime import date

def _get_base_dir() -> str:
    return os.environ.get(
        "APP_BASE_DIR",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


# Путь к файлу базы данных и каталогу документов (рядом с .exe при сборке PyInstaller)
DB_PATH = os.path.join(_get_base_dir(), "data", "orchestrator.db")
DOCUMENTS_DIR = os.path.join(_get_base_dir(), "documents")


def get_connection():
    """Возвращает подключение к базе данных."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Чтобы обращаться к полям по имени
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database():
    """Создаёт все таблицы если их ещё нет."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            role             TEXT DEFAULT 'viewer',
            email            TEXT,
            telegram_chat_id TEXT,
            caldav_url       TEXT,
            caldav_password  TEXT,
            created_at       TEXT DEFAULT (datetime('now'))
        )
    """)

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN max_chat_id TEXT")
    except Exception:
        pass

    # Таблица приборов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            type             TEXT NOT NULL,
            name             TEXT NOT NULL,
            inventory_number TEXT,
            serial_number    TEXT,
            location         TEXT,
            responsible_id   INTEGER REFERENCES users(id),
            note             TEXT,
            is_active        INTEGER DEFAULT 1,
            calendar_event_id TEXT,
            created_at       TEXT DEFAULT (datetime('now')),
            updated_at       TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            telegram_chat_id TEXT,
            phone TEXT,
            device_type TEXT
        )
    """)

    try:
        cursor.execute("ALTER TABLE devices ADD COLUMN responsible_fio TEXT DEFAULT ''")
    except Exception:
        pass

    # Таблица истории поверок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verifications (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id         INTEGER NOT NULL REFERENCES devices(id),
            verification_date TEXT,
            expiry_date       TEXT NOT NULL,
            result            TEXT DEFAULT 'пройдено',
            certificate_path  TEXT,
            comment           TEXT,
            created_by        INTEGER REFERENCES users(id),
            created_at        TEXT DEFAULT (datetime('now'))
        )
    """)

    # Справочник ответственных → MAX user_id (для рассылки)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS responsible_persons (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            fio           TEXT NOT NULL UNIQUE,
            max_user_id   INTEGER
        )
    """)

    try:
        cursor.execute("ALTER TABLE responsible_persons ADD COLUMN email TEXT")
    except Exception:
        pass

    # Таблица лога уведомлений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER REFERENCES devices(id),
            channel   TEXT,
            message   TEXT,
            sent_at   TEXT DEFAULT (datetime('now')),
            status    TEXT DEFAULT 'ok'
        )
    """)

    # Прикреплённые документы к прибору (файлы в documents/<device_id>/)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS device_documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            filename    TEXT NOT NULL,
            filepath    TEXT NOT NULL,
            uploaded_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Ключ-значение (CalDAV и др.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Представление: прибор + последняя поверка + статус светофора
    cursor.execute("DROP VIEW IF EXISTS v_device_status")
    cursor.execute("""
        CREATE VIEW v_device_status AS
        SELECT
            d.id,
            d.type,
            d.name,
            d.inventory_number,
            d.serial_number,
            d.location,
            d.responsible_id,
            u.name AS responsible_name,
            u.telegram_chat_id,
            d.note,
            d.is_active,
            v.expiry_date,
            v.verification_date,
            v.id AS verification_id,
            CASE
                WHEN v.expiry_date IS NULL THEN 'no_data'
                WHEN julianday(v.expiry_date) - julianday('now') > 60 THEN 'green'
                WHEN julianday(v.expiry_date) - julianday('now') > 7  THEN 'yellow'
                ELSE 'red'
            END AS status
        FROM devices d
        LEFT JOIN users u ON u.id = d.responsible_id
        LEFT JOIN verifications v ON v.id = (
            SELECT id FROM verifications
            WHERE device_id = d.id
            ORDER BY expiry_date DESC LIMIT 1
        )
        WHERE d.is_active = 1
    """)

    # Добавляем администратора по умолчанию если пользователей нет
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO users (name, role, email)
            VALUES ('Администратор', 'admin', '')
        """)

    conn.commit()
    conn.close()
    print(f"✅ База данных создана: {DB_PATH}")


def get_all_devices():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # удаляем мусорные строки без инвентарного номера
    cur.execute("""
        DELETE FROM devices
        WHERE inventory_number IS NULL
           OR TRIM(inventory_number) = ''
           OR TRIM(inventory_number) IN (
                'Инв. номер', '№', '1', '2', '3', '4', '5',
                'Местонахождение (склад/вагон)'
           )
    """)
    conn.commit()

    cur.execute("""
        SELECT
            d.id,
            d.type,
            d.name,
            d.inventory_number,
            d.serial_number,
            d.location,
            d.note,
            d.responsible_fio,
            v.expiry_date,
            v.verification_date,
            CASE
                WHEN v.expiry_date IS NULL THEN 'no_data'
                WHEN date(v.expiry_date) < date('now') THEN 'red'
                WHEN date(v.expiry_date) <= date('now', '+60 days') THEN 'yellow'
                ELSE 'green'
            END AS status
        FROM devices d
        LEFT JOIN (
            SELECT device_id,
                   MAX(expiry_date) AS expiry_date,
                   verification_date
            FROM verifications
            GROUP BY device_id
        ) v ON d.id = v.device_id
        WHERE d.inventory_number IS NOT NULL
          AND TRIM(d.inventory_number) != ''
          AND TRIM(d.inventory_number) NOT IN (
                'Инв. номер', '№', '1', '2', '3',
                'Местонахождение (склад/вагон)'
          )
        ORDER BY d.type, d.location
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_device_verifications(device_id):
    """Возвращает историю поверок для прибора."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM verifications
        WHERE device_id = ?
        ORDER BY expiry_date DESC
    """, (device_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_device(device_id: int) -> None:
    """Удаляет прибор, связанные поверки и записи лога уведомлений."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM notification_log WHERE device_id = ?", (device_id,))
    cur.execute("DELETE FROM verifications WHERE device_id = ?", (device_id,))
    cur.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    conn.commit()
    conn.close()
    doc_dir = os.path.join(DOCUMENTS_DIR, str(device_id))
    if os.path.isdir(doc_dir):
        shutil.rmtree(doc_dir, ignore_errors=True)


def update_responsible_fio(device_id: int, fio: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE devices SET responsible_fio = ? WHERE id = ?",
        (fio.strip(), device_id)
    )
    conn.commit()
    conn.close()


def get_location_choices(include: str | None = None) -> list[str]:
    """Уникальные места из журнала; при необходимости добавляет текущее значение."""
    devices = get_all_devices()
    locs = sorted(
        {
            str(d["location"]).strip()
            for d in devices
            if d.get("location") and str(d["location"]).strip()
        }
    )
    if include and str(include).strip():
        s = str(include).strip()
        if s not in locs:
            locs.append(s)
            locs.sort()
    return locs


def update_device_location(device_id: int, location: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE devices SET location = ?, updated_at = datetime('now') WHERE id = ?",
        (location.strip(), device_id),
    )
    conn.commit()
    conn.close()


def update_device_note(device_id: int, note: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE devices SET note = ?, updated_at = datetime('now') WHERE id = ?",
        (note.strip(), device_id),
    )
    conn.commit()
    conn.close()


def duplicate_device(source_device_id: int, new_inventory_number: str) -> int:
    """Копия прибора без истории поверок; возвращает id новой записи."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT type, name, serial_number, location, responsible_fio
        FROM devices WHERE id = ?
        """,
        (source_device_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError("Прибор не найден")
    name = row["name"] or row["type"] or "Прибор"
    cur.execute(
        """
        INSERT INTO devices (type, name, inventory_number, serial_number, location, responsible_fio)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            row["type"],
            name,
            new_inventory_number.strip(),
            row["serial_number"] or "",
            row["location"] or "",
            row["responsible_fio"] or "",
        ),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_responsible_persons_rows():
    """Все строки справочника ответственных (для GUI)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, fio, max_user_id, IFNULL(email, '') AS email
        FROM responsible_persons
        ORDER BY fio COLLATE NOCASE
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def upsert_responsible_person(fio: str, max_user_id: int | None) -> None:
    """Добавить или обновить строку по ФИО."""
    fio = (fio or "").strip()
    if not fio:
        return
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO responsible_persons (fio, max_user_id)
        VALUES (?, ?)
        ON CONFLICT(fio) DO UPDATE SET max_user_id = excluded.max_user_id
        """,
        (fio, max_user_id),
    )
    conn.commit()
    conn.close()


def get_responsible_email(fio: str) -> str:
    """Возвращает email ответственного по ФИО."""
    if not fio:
        return ""
    conn = get_connection()
    row = conn.execute(
        "SELECT email FROM responsible_persons WHERE fio=?",
        (fio.strip(),),
    ).fetchone()
    conn.close()
    return (row[0] or "") if row else ""


def set_responsible_person_email(fio: str, email: str) -> None:
    """Сохраняет email в справочнике по ФИО."""
    fio = (fio or "").strip()
    if not fio:
        return
    conn = get_connection()
    conn.execute(
        "UPDATE responsible_persons SET email = ? WHERE fio = ?",
        ((email or "").strip(), fio),
    )
    conn.commit()
    conn.close()


def was_notification_sent_today(device_id: int, channel: str) -> bool:
    """
    True, если для прибора уже есть запись в notification_log за сегодня
    для указанного канала (например 'email', 'MAX').
    """
    if not device_id:
        return False
    day = date.today().isoformat()
    conn = get_connection()
    row = conn.execute(
        """
        SELECT 1 FROM notification_log
        WHERE device_id = ?
          AND channel = ?
          AND substr(COALESCE(sent_at, ''), 1, 10) = ?
        LIMIT 1
        """,
        (device_id, channel, day),
    ).fetchone()
    conn.close()
    return row is not None


def was_digest_notification_sent_today(channel: str, recipient_marker: str) -> bool:
    """Сводка за сегодня уже уходила (device_id NULL, channel + message — маркер)."""
    day = date.today().isoformat()
    conn = get_connection()
    row = conn.execute(
        """
        SELECT 1 FROM notification_log
        WHERE device_id IS NULL
          AND channel = ?
          AND message = ?
          AND substr(COALESCE(sent_at, ''), 1, 10) = ?
        LIMIT 1
        """,
        (channel, recipient_marker, day),
    ).fetchone()
    conn.close()
    return row is not None


def log_digest_notification(channel: str, recipient_marker: str) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO notification_log (device_id, channel, message, status)
        VALUES (NULL, ?, ?, 'sent')
        """,
        (channel, recipient_marker),
    )
    conn.commit()
    conn.close()


def get_max_user_id_for_fio(fio: str) -> int | None:
    """Возвращает max_user_id для ФИО или None."""
    fio = (fio or "").strip()
    if not fio:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT max_user_id FROM responsible_persons WHERE fio = ?",
        (fio,),
    )
    row = cur.fetchone()
    conn.close()
    if row and row[0] is not None:
        return int(row[0])
    return None


def get_device_documents(device_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, filename, filepath, uploaded_at
        FROM device_documents
        WHERE device_id = ?
        ORDER BY uploaded_at DESC
        """,
        (device_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def attach_document(device_id: int, src_path: str) -> dict:
    """Копирует файл в documents/<device_id>/, сохраняет запись в БД."""
    dest_dir = os.path.join(DOCUMENTS_DIR, str(device_id))
    os.makedirs(dest_dir, exist_ok=True)

    filename = os.path.basename(src_path)
    dest_path = os.path.join(dest_dir, filename)

    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(dest_path):
        dest_path = os.path.join(dest_dir, f"{base}_{counter}{ext}")
        filename = f"{base}_{counter}{ext}"
        counter += 1

    shutil.copy2(src_path, dest_path)

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO device_documents (device_id, filename, filepath)
        VALUES (?, ?, ?)
        """,
        (device_id, filename, dest_path),
    )
    conn.commit()
    conn.close()
    return {"filename": filename, "filepath": dest_path}


def delete_document(doc_id: int) -> None:
    conn = get_connection()
    row = conn.execute(
        "SELECT filepath FROM device_documents WHERE id = ?",
        (doc_id,),
    ).fetchone()
    if row:
        try:
            os.remove(row["filepath"])
        except FileNotFoundError:
            pass
        conn.execute("DELETE FROM device_documents WHERE id = ?", (doc_id,))
        conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def set_device_calendar_event_id(device_id: int, event_uid: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE devices SET calendar_event_id = ? WHERE id = ?",
        (event_uid, device_id),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_database()
    print("Тест: получаем список приборов...")
    devices = get_all_devices()
    print(f"Приборов в базе: {len(devices)}")
