import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from core.notifier import send_message, check_and_notify

chat_id = os.getenv("ADMIN_CHAT_ID")
print(f"Отправляем тест на user_id={chat_id}...")
ok = send_message(chat_id, "PoverkiVSE — подключён и работает!")
print("Отправлено!" if ok else "Ошибка")

print("\nПроверка приборов (dry_run)...")
result = check_and_notify(dry_run=True)
print(f"Приборов с истекающим сроком: {len(result['messages'])}")
print(f"Пропущено (в норме): {result['skipped']}")

if result["messages"]:
    print(f"\nОтправляем реальные уведомления...")
    result2 = check_and_notify(dry_run=False)
    print(f"Отправлено: {result2['sent']}")
    print(f"Ошибок:    {result2['errors']}")
else:
    print("Приборов с истекающим сроком нет — уведомлять некого.")
