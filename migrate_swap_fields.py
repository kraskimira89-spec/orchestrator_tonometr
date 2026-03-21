"""
Миграция: физически меняет местами значения
inventory_number ↔ location у всех записей в таблице devices.

Запускать ОДИН РАЗ.
"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRIMARY_DB_PATH = os.path.join(BASE_DIR, "data", "devices.db")
FALLBACK_DB_PATH = os.path.join(BASE_DIR, "data", "orchestrator.db")
DB_PATH = PRIMARY_DB_PATH if os.path.exists(PRIMARY_DB_PATH) else FALLBACK_DB_PATH


def main():
    print(f"БД: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Проверяем сколько записей до
    cur.execute("SELECT COUNT(*) FROM devices")
    total = cur.fetchone()[0]
    print(f"Всего записей: {total}")

    # Показываем 3 записи ДО
    print("\n--- ДО (первые 3 записи) ---")
    cur.execute("SELECT id, inventory_number, location FROM devices LIMIT 3")
    for row in cur.fetchall():
        print(f"  id={row[0]} | inv={row[1]} | loc={row[2]}")

    # Проверяем — не запускали ли уже
    # Признак: если в inventory_number лежат длинные строки с "ВАГОН" — значит надо менять
    cur.execute(
        """
        SELECT COUNT(*) FROM devices
        WHERE inventory_number LIKE '%ВАГОН%'
           OR inventory_number LIKE '%ССК%'
           OR inventory_number LIKE '%Склад%'
           OR inventory_number LIKE '%Бурение%'
        """
    )
    wrong_count = cur.fetchone()[0]

    if wrong_count == 0:
        print("\n✅ Данные уже в правильном порядке — миграция не нужна!")
        conn.close()
        return

    print(f"\n⚠️  Найдено {wrong_count} записей где inventory_number содержит название места.")
    print("Начинаю swap...")

    # SWAP через временную колонку
    try:
        cur.execute("ALTER TABLE devices ADD COLUMN _tmp_swap TEXT")
    except Exception:
        pass
    cur.execute("UPDATE devices SET _tmp_swap = inventory_number")
    cur.execute("UPDATE devices SET inventory_number = location")
    cur.execute("UPDATE devices SET location = _tmp_swap")
    cur.execute("UPDATE devices SET _tmp_swap = NULL")

    # Удаляем временную колонку (SQLite 3.35+)
    try:
        cur.execute("ALTER TABLE devices DROP COLUMN _tmp_swap")
    except Exception:
        # Если SQLite старый — просто оставим NULL-колонку, не критично
        print("  (временная колонка _tmp_swap осталась, SQLite < 3.35 — не критично)")

    conn.commit()

    # Показываем 3 записи ПОСЛЕ
    print("\n--- ПОСЛЕ (первые 3 записи) ---")
    cur.execute("SELECT id, inventory_number, location FROM devices LIMIT 3")
    for row in cur.fetchall():
        print(f"  id={row[0]} | inv={row[1]} | loc={row[2]}")

    conn.close()
    print(f"\n✅ Готово! Поменяно местами {wrong_count} записей.")


if __name__ == "__main__":
    main()
