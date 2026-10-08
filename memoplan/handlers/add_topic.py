"""
Conversation handler for adding a new Topic to MemoPlan.
"""
from datetime import datetime, timezone
import html
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from memoplan.database import db
from memoplan.presets import PRESETS, get_preset
from memoplan.scheduler import calculate_initial_review, format_time_diff_future, to_user_tz
from memoplan.ui.keyboards import (
    get_cancel_keyboard,
    get_presets_keyboard,
    get_skip_notes_keyboard,
)

# Conversation states
STATE_TITLE, STATE_NOTES, STATE_PRESET = range(3)


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start topic creation dialog."""
    # Clear any previous creation cache
    context.user_data.pop("new_topic", None)
    context.user_data["new_topic"] = {}

    prompt_text = (
        "➕ <b>ДОБАВЛЕНИЕ НОВОЙ ТЕМЫ</b>\n"
        "────────────────────────\n"
        "Введите <b>заголовок темы</b>.\n\n"
        "<i>Например: «Команда grep», «SQL Оконные функции», «Алгоритм Дейкстры»</i>"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            prompt_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard("add_cancel"),
        )
    elif update.message:
        await update.message.reply_text(
            prompt_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard("add_cancel"),
        )

    return STATE_TITLE


async def add_title_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save title and ask for notes."""
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Пожалуйста, введите непустое название темы:")
        return STATE_TITLE

    context.user_data["new_topic"]["title"] = title

    prompt_text = (
        f"📌 Тема: <b>{html.escape(title)}</b>\n\n"
        "Теперь отправьте <b>шпаргалку, заметки или контекст</b>.\n"
        "<i>(Краткие флаги, пример команды, ссылка на конспект или объяснение своими словами)</i>\n\n"
        "Либо нажмите «Пропустить», если хотите учить без шпаргалки."
    )

    await update.message.reply_text(
        prompt_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_skip_notes_keyboard(),
    )
    return STATE_NOTES


async def add_notes_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save notes and ask for interval preset."""
    notes = update.message.text.strip()
    context.user_data["new_topic"]["notes"] = notes
    return await prompt_preset_selection(update, context)


async def add_notes_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip notes and ask for preset."""
    await update.callback_query.answer()
    context.user_data["new_topic"]["notes"] = None
    return await prompt_preset_selection(update, context)


async def prompt_preset_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display preset choice buttons."""
    title = context.user_data["new_topic"].get("title", "")

    lines = [
        f"🎯 Выберите <b>режим интервалов</b> для темы «<b>{html.escape(title)}</b>»:\n",
    ]
    for p in PRESETS.values():
        lines.append(f"• {p.emoji} <b>{p.title}:</b> {p.description}")

    text = "\n".join(lines)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_presets_keyboard("new_preset"),
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_presets_keyboard("new_preset"),
        )

    return STATE_PRESET


async def add_preset_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save preset and finalize topic creation."""
    query = update.callback_query
    await query.answer()

    preset_id = query.data.split(":")[-1]
    user_id = query.from_user.id
    settings = db.get_or_create_user(user_id)

    topic_data = context.user_data.get("new_topic", {})
    title = topic_data.get("title", "Без названия")
    notes = topic_data.get("notes")

    preset = get_preset(preset_id)
    # Initial interval calculation: step 0 -> 1 (+20m with sleep adjustment)
    first_review_at = calculate_initial_review(preset, settings)

    topic = db.create_topic(
        user_id=user_id,
        title=title,
        notes=notes,
        stage=0,
        preset_name=preset_id,
        next_review_at=first_review_at,
    )

    first_local = to_user_tz(first_review_at, settings.timezone_offset)
    time_str = format_time_diff_future(first_review_at, settings.timezone_offset)

    success_text = (
        "✅ <b>ТЕМА УСПЕШНО СОЗДАНА!</b>\n"
        "────────────────────────\n"
        f"📌 <b>Название:</b> <code>{html.escape(topic.title)}</code>\n"
        f"🎯 <b>Сетка:</b> {preset.emoji} {preset.title}\n"
        f"📊 <b>Начальный этап:</b> 0 из {preset.total_steps}\n\n"
        f"⏱ <b>Первичное закрепление (шаг 0 → 1):</b>\n"
        f"Через <b>{time_str}</b> (<code>{first_local.strftime('%H:%M')}</code>)\n\n"
        "💡 <i>Когда наступит время, бот напомнит вам о повторении.</i>"
    )

    await query.edit_message_text(success_text, parse_mode=ParseMode.HTML)
    context.user_data.pop("new_topic", None)
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel creation."""
    context.user_data.pop("new_topic", None)
    msg = "❌ Добавление темы отменено."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg)
    elif update.message:
        await update.message.reply_text(msg)
    return ConversationHandler.END


def get_add_topic_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            MessageHandler(filters.Regex("^➕ (Новая тема|Добавить тему)$"), add_start),
            CallbackQueryHandler(add_start, pattern="^action_add_topic$"),
        ],
        states={
            STATE_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_title_received),
            ],
            STATE_NOTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_notes_received),
                CallbackQueryHandler(add_notes_skip, pattern="^notes_skip$"),
            ],
            STATE_PRESET: [
                CallbackQueryHandler(add_preset_selected, pattern="^new_preset:"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", add_cancel),
            CallbackQueryHandler(add_cancel, pattern="^add_cancel$"),
        ],
        allow_reentry=True,
        per_message=False,
    )
