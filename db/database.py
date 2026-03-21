import sqlite3
import os
from datetime import date

# Путь к файлу базы данных
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "orchestrator.db")


def get_connection():
    """Возвращает подключение к базе данных."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Чтобы обращаться к полям по имени
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database():
    """Создаёт все таблицы если их ещё нет."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
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
            d.inventory_number,
            d.location,
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
    return rows


def update_responsible_fio(device_id: int, fio: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE devices SET responsible_fio = ? WHERE id = ?",
        (fio.strip(), device_id)
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_database()
    print("Тест: получаем список приборов...")
    devices = get_all_devices()
    print(f"Приборов в базе: {len(devices)}")
