"""
Handlers for browsing, managing, and editing Topics.
"""
from datetime import datetime, timezone
import html
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from memoplan.database import db
from memoplan.ui.formatters import format_topic_detail
from memoplan.ui.keyboards import (
    get_cancel_keyboard,
    get_delete_confirm_keyboard,
    get_topic_actions_keyboard,
    get_topics_pagination_keyboard,
)


async def topics_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show paginated list of all topics."""
    user = update.effective_user
    if not user:
        return

    page = 1
    if update.callback_query:
        parts = update.callback_query.data.split(":")
        if len(parts) > 1 and parts[1].isdigit():
            page = int(parts[1])
        await update.callback_query.answer()

    topics = db.get_user_topics(user.id)
    if not topics:
        empty_text = (
            "📚 <b>ВАШИ ТЕМЫ</b>\n"
            "────────────────────────\n"
            "У вас пока нет добавленных тем.\n\n"
            "Нажмите «➕ Добавить тему», чтобы начать!"
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(
                empty_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_topics_pagination_keyboard([], page=1),
            )
        elif update.message:
            await update.message.reply_text(
                empty_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_topics_pagination_keyboard([], page=1),
            )
        return

    text = f"📚 <b>ВСЕ ТЕМЫ (Всего: {len(topics)})</b>\nВыберите тему для просмотра или управления:"
    keyboard = get_topics_pagination_keyboard(topics, page=page, per_page=6)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except Exception:
            await update.callback_query.message.reply_text(
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


async def topic_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View details of a single topic."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    topic_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

    user_id = query.from_user.id
    settings = db.get_or_create_user(user_id)
    topic = db.get_topic(topic_id)

    if not topic or topic.user_id != user_id:
        await query.edit_message_text("❌ Тема не найдена.")
        return

    history = db.get_topic_history(topic.id)
    detail_text = format_topic_detail(topic, settings, history)
    keyboard = get_topic_actions_keyboard(topic, page=page)

    await query.edit_message_text(
        detail_text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def topic_toggle_pause_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle pause / resume status."""
    query = update.callback_query
    parts = query.data.split(":")
    topic_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
    user_id = query.from_user.id

    topic = db.get_topic(topic_id)
    if not topic or topic.user_id != user_id:
        await query.answer("Тема не найдена")
        return

    new_status = "active" if topic.is_paused else "paused"
    db.update_topic_status(topic.id, user_id, new_status)

    alert_msg = "▶️ Тема возобновлена!" if new_status == "active" else "⏸ Тема поставлена на паузу."
    await query.answer(alert_msg)

    # Refresh details
    topic = db.get_topic(topic_id)
    settings = db.get_or_create_user(user_id)
    history = db.get_topic_history(topic.id)

    await query.edit_message_text(
        format_topic_detail(topic, settings, history),
        parse_mode=ParseMode.HTML,
        reply_markup=get_topic_actions_keyboard(topic, page=page),
    )


async def topic_delete_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt confirmation before deleting topic."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    topic_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

    topic = db.get_topic(topic_id)
    if not topic:
        await query.answer("Тема не найдена")
        return

    escaped_title = html.escape(topic.title)
    prompt_text = (
        f"⚠️ <b>Удаление темы</b>\n\n"
        f"Вы действительно хотите безвозвратно удалить тему «<b>{escaped_title}</b>» вместе со всей историей?"
    )

    await query.edit_message_text(
        prompt_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_delete_confirm_keyboard(topic_id, page=page),
    )


async def topic_delete_confirmed_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute deletion."""
    query = update.callback_query
    parts = query.data.split(":")
    topic_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
    user_id = query.from_user.id

    db.delete_topic(topic_id, user_id)
    await query.answer("Тема удалена!")

    # Return to topics list
    topics = db.get_user_topics(user_id)
    text = f"📚 <b>ВСЕ ТЕМЫ (Всего: {len(topics)})</b>\nТема успешно удалена."
    keyboard = get_topics_pagination_keyboard(topics, page=page, per_page=6)

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def topic_edit_notes_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt user to send new notes."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    topic_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

    topic = db.get_topic(topic_id)
    if not topic:
        return

    context.user_data["editing_notes_topic_id"] = topic_id
    context.user_data["editing_notes_page"] = page

    text = (
        f"✏️ <b>Редактирование шпаргалки</b> для темы «<b>{html.escape(topic.title)}</b>»\n\n"
        "Отправьте сообщением новый текст заметок/шпаргалки.\n"
        "<i>(Или отправьте дефис «-», чтобы очистить заметки)</i>"
    )

    await query.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard("cancel_edit_notes"),
    )


async def topic_edit_notes_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive new notes text."""
    topic_id = context.user_data.get("editing_notes_topic_id")
    page = context.user_data.get("editing_notes_page", 1)

    if not topic_id:
        return

    new_text = update.message.text.strip()
    if new_text == "-":
        new_text = ""

    user_id = update.effective_user.id
    db.update_topic_notes(topic_id, user_id, new_text)

    context.user_data.pop("editing_notes_topic_id", None)
    context.user_data.pop("editing_notes_page", None)

    await update.message.reply_text("✅ Заметки к теме успешно обновлены!")

    topic = db.get_topic(topic_id)
    if topic:
        settings = db.get_or_create_user(user_id)
        history = db.get_topic_history(topic.id)
        await update.message.reply_text(
            format_topic_detail(topic, settings, history),
            parse_mode=ParseMode.HTML,
            reply_markup=get_topic_actions_keyboard(topic, page=page),
        )


async def cancel_edit_notes_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel notes editing."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("editing_notes_topic_id", None)
    context.user_data.pop("editing_notes_page", None)
    await query.edit_message_text("❌ Редактирование заметок отменено.")


def register_topics_handlers(app) -> None:
    app.add_handler(CommandHandler("topics", topics_list_handler))
    app.add_handler(MessageHandler(filters.Regex("^📚 Все темы$"), topics_list_handler))
    app.add_handler(CallbackQueryHandler(topics_list_handler, pattern="^topics_page:"))
    app.add_handler(CallbackQueryHandler(topic_view_handler, pattern="^topic_view:"))
    app.add_handler(CallbackQueryHandler(topic_toggle_pause_handler, pattern="^topic_toggle_pause:"))
    app.add_handler(CallbackQueryHandler(topic_delete_prompt_handler, pattern="^topic_delete_prompt:"))
    app.add_handler(CallbackQueryHandler(topic_delete_confirmed_handler, pattern="^topic_delete_confirmed:"))
    app.add_handler(CallbackQueryHandler(topic_edit_notes_prompt, pattern="^topic_edit_notes:"))
    app.add_handler(CallbackQueryHandler(cancel_edit_notes_handler, pattern="^cancel_edit_notes$"))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            topic_edit_notes_message,
        ),
        group=2,
    )
