"""
Application builder and Telegram bot initialization.
"""
import logging
import warnings
from telegram import BotCommand
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

warnings.filterwarnings("ignore", category=PTBUserWarning)

from memoplan.config import config
from memoplan.handlers.add_topic import get_add_topic_conversation_handler
from memoplan.handlers.archive import register_archive_handlers
from memoplan.handlers.common import demo_handler, help_handler, queue_handler, start_handler
from memoplan.handlers.review import register_review_handlers
from memoplan.handlers.settings import register_settings_handlers
from memoplan.handlers.stats import register_stats_handlers
from memoplan.handlers.topics import register_topics_handlers
from memoplan.notifier import NotifierService

logger = logging.getLogger(__name__)


async def setup_bot_commands(application: Application) -> None:
    """Register menu commands in Telegram UI autocomplete."""
    commands = [
        BotCommand("start", "Главное меню и очередь"),
        BotCommand("queue", "Очередь повторений на сегодня"),
        BotCommand("add", "Добавить новую тему"),
        BotCommand("topics", "Список всех тем"),
        BotCommand("archive", "Долговременная память"),
        BotCommand("stats", "Статистика обучения"),
        BotCommand("settings", "Настройки сна и уведомлений"),
        BotCommand("help", "Справка по интервалам"),
    ]
    try:
        await application.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning(f"Failed to set bot commands: {e}")


from telegram.request import HTTPXRequest

def create_bot_application(token: str) -> Application:
    """Create and configure Telegram Application instance."""
    request_kwargs = {
        "connect_timeout": 20.0,
        "read_timeout": 20.0,
        "write_timeout": 20.0,
    }
    if config.PROXY_URL:
        request_kwargs["proxy"] = config.PROXY_URL
        logger.info(f"Using proxy for Telegram API: {config.PROXY_URL}")

    request = HTTPXRequest(**request_kwargs)
    app = ApplicationBuilder().token(token).request(request).build()

    # Create background notifier service
    notifier = NotifierService(app.bot)

    async def on_post_init(application: Application) -> None:
        await setup_bot_commands(application)
        notifier.start()
        logger.info("MemoPlan bot initialized successfully.")

    async def on_post_shutdown(application: Application) -> None:
        notifier.stop()
        logger.info("MemoPlan bot stopped.")

    app.post_init = on_post_init
    app.post_shutdown = on_post_shutdown

    # 1. Common command handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("queue", queue_handler))
    app.add_handler(CommandHandler("demo", demo_handler))

    # Reply keyboard routes for main menu
    app.add_handler(MessageHandler(filters.Regex("^📥 Очередь на сегодня$"), queue_handler))
    app.add_handler(CallbackQueryHandler(queue_handler, pattern="^queue_refresh$"))

    # 2. Conversation handler for adding new topics
    app.add_handler(get_add_topic_conversation_handler())

    # 3. Spaced repetition review handlers
    register_review_handlers(app)

    # 4. Topics management handlers
    register_topics_handlers(app)

    # 5. Archive & Long-term memory handlers
    register_archive_handlers(app)

    # 6. Statistics handlers
    register_stats_handlers(app)

    # 7. Settings handlers
    register_settings_handlers(app)

    return app
