"""
MemoPlan Telegram Bot entrypoint.
"""
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memoplan.config import BASE_DIR, config
from memoplan.bot import create_bot_application


def setup_logging():
    logging.basicConfig(
        format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )
    # Suppress verbose httpx request logs
    logging.getLogger("httpx").setLevel(logging.WARNING)


def prompt_for_token_if_needed() -> str:
    token = config.BOT_TOKEN
    if token and token != "your_telegram_bot_token_here":
        return token

    env_file = BASE_DIR / ".env"

    print("=" * 60)
    print("👋 Добро пожаловать в MemoPlan (Telegram Bot)!")
    print("=" * 60)
    print("⚠️ Токен бота (TELEGRAM_BOT_TOKEN) еще не настроен.")
    print("\nКак получить токен:")
    print("  1. Откройте Telegram и напишите боту @BotFather")
    print("  2. Отправьте команду /newbot и выберите имя бота")
    print("  3. Скопируйте выданный API токен (например: 123456789:ABCdef-...)")
    print("=" * 60)

    try:
        user_input = input("\n👉 Введите TELEGRAM_BOT_TOKEN (или нажмите Enter для выхода): ").strip()
    except (EOFError, KeyboardInterrupt):
        user_input = ""

    if not user_input:
        print("\nТокен не введен. Вы можете указать его в файле .env:")
        print(f"  {env_file}")
        sys.exit(1)

    # Save to .env
    env_content = f"TELEGRAM_BOT_TOKEN={user_input}\n"
    with open(env_file, "w") as f:
        f.write(env_content)
    print(f"✅ Токен сохранен в {env_file}!\n")
    return user_input


def main():
    setup_logging()
    token = prompt_for_token_if_needed()

    print("\n🚀 Запуск MemoPlan бота...")
    app = create_bot_application(token)
    print("🤖 Бот успешно запущен и слушает входящие сообщения (Long Polling)!")
    print("Нажмите Ctrl+C для остановки.\n")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
