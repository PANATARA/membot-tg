"""
Handlers for Mastered topics archive («Навсегда в долговременной памяти»).
"""
import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from memoplan.database import db
from memoplan.presets import get_preset


async def archive_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display mastered topics in long-term memory."""
    user = update.effective_user
    if not user:
        return

    topics = db.get_user_topics(user.id, status="mastered")

    lines = [
        "🏆 <b>АРХИВ: НАВСЕГДА В ДОЛГОВРЕМЕННОЙ ПАМЯТИ</b>",
        "────────────────────────",
    ]

    if not topics:
        lines.append(
            "<i>Здесь будут отображаться темы, успешно прошедшие все этапы сетки повторений.</i>\n\n"
            "Пока этот раздел пуст, но продолжайте регулярные повторения, и первые темы скоро появятся здесь!"
        )
    else:
        lines.append(f"Всего освоено тем: <b>{len(topics)}</b> 🎖\n")
        for t in topics:
            preset = get_preset(t.preset_name)
            escaped_title = html.escape(t.title)
            lines.append(f"✅ <b>{escaped_title}</b> (сетка: {preset.title}, пройдены все {preset.total_steps} эт.)")

    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Вернуться в очередь", callback_data="queue_refresh")]
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


def register_archive_handlers(app) -> None:
    app.add_handler(CommandHandler("archive", archive_handler))
    app.add_handler(MessageHandler(filters.Regex("^🏆 Долговременная память$"), archive_handler))
