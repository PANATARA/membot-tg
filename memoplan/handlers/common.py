"""
Common command handlers: /start, /help, and main menu routing.
"""
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from memoplan.database import db
from memoplan.presets import PRESETS
from memoplan.scheduler import split_topics_queue
from memoplan.ui.formatters import format_queue_message
from memoplan.ui.keyboards import (
    get_main_reply_keyboard,
    get_queue_inline_keyboard,
)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    if not user:
        return

    settings = db.get_or_create_user(user.id)
    user_topics = db.get_user_topics(user.id)

    # If first time user has 0 topics, offer demo topics
    welcome_text = (
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        "Добро пожаловать в <b>MemoPlan</b> — систему интервального повторения на основе <b>«Тем»</b>.\n\n"
        "🎯 <b>Главные особенности:</b>\n"
        "• <b>Темы вместо карточек:</b> вы отслеживаете статус и таймлайн закрепления темы.\n"
        "• <b>Умная сетка интервалов:</b> от 20 минут до 30 дней и финального перехода в Долговременную память.\n"
        "• <b>Дневной батчинг (Sleep-aware):</b> если повторение выпадает на ночь, бот переносит его на утро.\n"
        "• <b>Уведомления без спама:</b> группированные напоминания только о созревших темах.\n"
    )

    if not user_topics:
        welcome_text += "\n💡 <i>У вас пока нет тем. Мы можем загрузить демо-примеры или создать вашу первую тему!</i>"

    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_reply_keyboard(),
    )

    # Show current queue
    queue = split_topics_queue(user_topics)
    msg_text = format_queue_message(queue, settings)
    due_count = len(queue.get("due", []))

    await update.message.reply_text(
        msg_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_queue_inline_keyboard(due_count),
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    lines = [
        "📖 <b>СПРАВКА ПО MEMOPLAN</b>\n",
        "<b>Как устроена система интервалов:</b>",
        "Каждая тема проходит через шаги закрепления:",
        "• <b>Шаг 0 → 1:</b> +20 мин (первичное закрепление)",
        "• <b>Шаг 1 → 2:</b> +12 часов (вечером того же дня / на след. утро)",
        "• <b>Шаг 2 → 3:</b> +24 часа (1 день)",
        "• <b>Шаг 3 → 4:</b> +3 дня",
        "• <b>Шаг 4 → 5:</b> +7 дней",
        "• <b>Шаг 5 → 6:</b> +14 дней",
        "• <b>Шаг 6 → 7:</b> +30 дней",
        "• <b>Шаг 7:</b> 🏆 Переход в <i>«Долговременную память»</i>\n",
        "<b>При повторении темы вы выбираете:</b>",
        "🟢 <b>Помню отлично:</b> шаг +1",
        "🟡 <b>Вспомнил с трудом:</b> закрепление на том же шаге",
        "🔴 <b>Забыл напрочь:</b> сброс на шаг 1 (+20 мин), нейроны закрепляются заново\n",
        "<b>Команды бота:</b>",
        "/start — Главное меню и текущая очередь",
        "/add — Создать новую тему",
        "/queue — Очередь на сегодня",
        "/topics — Список всех тем",
        "/archive — Архив долговременной памяти",
        "/stats — Статистика и аналитика",
        "/settings — Настройки сна и уведомлений",
        "/demo — Загрузить демонстрационные темы",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def queue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display current queue."""
    user = update.effective_user
    if not user:
        return

    settings = db.get_or_create_user(user.id)
    user_topics = db.get_user_topics(user.id)
    queue = split_topics_queue(user_topics)
    msg_text = format_queue_message(queue, settings)
    due_count = len(queue.get("due", []))

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            msg_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_queue_inline_keyboard(due_count),
        )
    elif update.message:
        await update.message.reply_text(
            msg_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_queue_inline_keyboard(due_count),
        )


async def demo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Load demo topics for the user."""
    user = update.effective_user
    if not user:
        return

    db.create_demo_topics(user.id)
    msg = (
        "🎁 <b>Демонстрационные темы успешно загружены!</b>\n\n"
        "Мы создали для вас темы на разных этапах (включая готовую к повторению прямо сейчас!).\n"
        "Откройте «📥 Очередь на сегодня», чтобы опробовать повторение."
    )

    if update.callback_query:
        await update.callback_query.answer("Демо-темы загружены!")
        settings = db.get_or_create_user(user.id)
        queue = split_topics_queue(db.get_user_topics(user.id))
        await update.callback_query.edit_message_text(
            format_queue_message(queue, settings),
            parse_mode=ParseMode.HTML,
            reply_markup=get_queue_inline_keyboard(len(queue.get("due", []))),
        )
    elif update.message:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
