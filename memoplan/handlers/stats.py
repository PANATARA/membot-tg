"""
Handlers for Statistics and Progress Dashboard.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from memoplan.database import db
from memoplan.ui.formatters import format_stats


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed user learning statistics."""
    user = update.effective_user
    if not user:
        return

    stats = db.get_user_stats(user.id)
    text = format_stats(stats)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Очередь на сегодня", callback_data="queue_refresh"),
            InlineKeyboardButton("🔄 Обновить", callback_data="show_stats"),
        ]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    elif update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


def register_stats_handlers(app) -> None:
    app.add_handler(CommandHandler("stats", stats_handler))
    app.add_handler(MessageHandler(filters.Regex("^📊 Статистика$"), stats_handler))
    app.add_handler(CallbackQueryHandler(stats_handler, pattern="^show_stats$"))
