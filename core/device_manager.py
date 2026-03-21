import sys
from pathlib import Path

# Запуск как `python core/device_manager.py` из корня проекта
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from db.database import get_all_devices, init_database


def format_status(status: str) -> str:
    """Преобразует код статуса в цветной значок."""
    if status == "green":
        return "🟢"
    if status == "yellow":
        return "🟡"
    if status == "red":
        return "🔴"
    return "⚪"


def print_devices_table():
    """Выводит в консоль простую таблицу приборов с их статусами."""
    init_database()  # на всякий случай убеждаемся, что БД есть
    devices = get_all_devices()

    if not devices:
        print("Приборов в базе пока нет.")
        return

    headers = [
        "ID",
        "Тип",
        "Наименование",
        "Инв.№",
        "Место",
        "Дата окончания",
        "Статус",
        "Ответственный",
    ]
    print("-" * 120)
    print(
        f"{headers[0]:<4} {headers[1]:<10} {headers[2]:<25} "
        f"{headers[3]:<12} {headers[4]:<25} {headers[5]:<12} "
        f"{headers[6]:<6} {headers[7]:<15}"
    )
    print("-" * 120)

    for row in devices:
        expiry = row["expiry_date"] or ""
        status_icon = format_status(row["status"])
        responsible = row["responsible_name"] or ""
        print(
            f"{row['id']:<4} {row['type']:<10} {row['name'][:25]:<25} "
            f"{(row['inventory_number'] or ''):<12} "
            f"{(row['location'] or '')[:25]:<25} "
            f"{expiry:<12} {status_icon:<6} {responsible[:15]:<15}"
        )

    print("-" * 120)


if __name__ == "__main__":
    print_devices_table()
