"""
Interactive spaced repetition review session handlers.
"""
from datetime import datetime, timezone
import html
from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from memoplan.database import db
from memoplan.models import ReviewLog, Topic
from memoplan.scheduler import calculate_review_outcome, now_utc
from memoplan.ui.formatters import format_review_card, format_review_result
from memoplan.ui.keyboards import get_queue_inline_keyboard, get_review_card_keyboard


async def start_review_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initialize review queue and display first card."""
    user = update.effective_user
    if not user:
        return

    due_topics = db.get_due_topics(user.id)
    if not due_topics:
        empty_msg = (
            "🟢 <b>Все темы на данный момент повторены!</b>\n\n"
            "В очереди нет тем, требующих закрепления прямо сейчас.\n"
            "Вы можете отдохнуть или добавить новую тему."
        )
        if update.callback_query:
            await update.callback_query.answer("Нет тем для повторения!")
            await update.callback_query.edit_message_text(
                empty_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=get_queue_inline_keyboard(0),
            )
        elif update.message:
            await update.message.reply_text(
                empty_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=get_queue_inline_keyboard(0),
            )
        return

    # Store queue in user context
    context.user_data["review_queue"] = [t.id for t in due_topics]
    context.user_data["review_index"] = 0

    if update.callback_query:
        await update.callback_query.answer()

    await render_review_card(update, context, revealed=False)


async def render_review_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    revealed: bool = False,
) -> None:
    """Render topic card for current item in review queue."""
    user = update.effective_user
    queue: List[int] = context.user_data.get("review_queue", [])
    index: int = context.user_data.get("review_index", 0)

    # Check if session completed
    if index >= len(queue):
        await finish_review_session(update, context)
        return

    topic_id = queue[index]
    topic = db.get_topic(topic_id)

    # If topic was deleted or changed, skip
    if not topic or not topic.is_active:
        context.user_data["review_index"] += 1
        await render_review_card(update, context, revealed=False)
        return

    card_text = format_review_card(
        topic=topic,
        queue_index=index + 1,
        queue_total=len(queue),
        revealed=revealed,
    )
    keyboard = get_review_card_keyboard(
        topic_id=topic.id,
        revealed=revealed,
        notes_available=bool(topic.notes),
    )

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                card_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except Exception:
            await update.callback_query.message.reply_text(
                card_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
    elif update.message:
        await update.message.reply_text(
            card_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


async def review_reveal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reveal notes / cheatsheet for the current card."""
    query = update.callback_query
    await query.answer("Шпаргалка открыта")
    await render_review_card(update, context, revealed=True)


async def review_rate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle rating button click (easy, hard, again)."""
    query = update.callback_query
    parts = query.data.split(":")
    topic_id = int(parts[1])
    rating = parts[2]

    user_id = query.from_user.id
    settings = db.get_or_create_user(user_id)
    topic = db.get_topic(topic_id)

    if not topic:
        await query.answer("Тема не найдена")
        context.user_data["review_index"] += 1
        await render_review_card(update, context, revealed=False)
        return

    old_stage = topic.stage

    # Calculate outcome using scheduler
    new_stage, next_dt, new_status = calculate_review_outcome(
        topic=topic,
        rating=rating,
        settings=settings,
        base_time=now_utc(),
    )

    # Update database
    topic.stage = new_stage
    topic.next_review_at = next_dt or now_utc()
    topic.status = new_status
    topic.last_notified_at = None
    db.update_topic(topic)

    # Save log
    db.add_review_log(
        ReviewLog(
            id=None,
            topic_id=topic.id,
            user_id=user_id,
            reviewed_at=now_utc(),
            rating=rating,
            old_stage=old_stage,
            new_stage=new_stage,
        )
    )

    toast_msg = "🟢 Запомнили!" if rating == "easy" else ("🟡 С трудом" if rating == "hard" else "🔴 Сброс на 1 шаг")
    await query.answer(toast_msg)

    # Format result message
    result_text = format_review_result(
        topic=topic,
        rating=rating,
        new_stage=new_stage,
        next_review_at=next_dt,
        status=new_status,
        settings=settings,
    )

    # Advance queue index
    context.user_data["review_index"] += 1
    next_index = context.user_data["review_index"]
    queue = context.user_data.get("review_queue", [])
    remaining = len(queue) - next_index

    if remaining > 0:
        next_button = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"➡️ Следующая тема ({remaining} ост.)", callback_data="review_next_step")],
            [InlineKeyboardButton("⏹ Завершить сейчас", callback_data="review_exit")],
        ])
    else:
        next_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎉 Завершить сессию", callback_data="review_next_step")]
        ])

    await query.edit_message_text(
        result_text,
        parse_mode=ParseMode.HTML,
        reply_markup=next_button,
    )


async def review_next_step_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Move to next topic after reading verdict."""
    query = update.callback_query
    await query.answer()
    await render_review_card(update, context, revealed=False)


async def review_skip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Skip topic for now."""
    query = update.callback_query
    await query.answer("Тема отложена")
    context.user_data["review_index"] += 1
    await render_review_card(update, context, revealed=False)


async def review_exit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exit review session early."""
    query = update.callback_query
    await query.answer("Сессия завершена")
    context.user_data.pop("review_queue", None)
    context.user_data.pop("review_index", None)

    user_id = query.from_user.id
    settings = db.get_or_create_user(user_id)
    from memoplan.scheduler import split_topics_queue
    from memoplan.ui.formatters import format_queue_message

    queue = split_topics_queue(db.get_user_topics(user_id))
    msg_text = format_queue_message(queue, settings)
    due_count = len(queue.get("due", []))

    await query.edit_message_text(
        msg_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_queue_inline_keyboard(due_count),
    )


async def finish_review_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display celebration screen when queue is finished."""
    context.user_data.pop("review_queue", None)
    context.user_data.pop("review_index", None)

    finish_text = (
        "🎉 <b>СЕССИЯ ПОВТОРЕНИЯ ЗАВЕРШЕНА!</b>\n"
        "────────────────────────\n"
        "Отличная работа! Все созревшие темы повторены.\n\n"
        "🧠 <i>Регулярность — главный ключ к созданию прочных долговременных синапсов.</i>\n\n"
        "Мы пришлём вам ненавязчивое уведомление, когда созреют следующие темы!"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Открыть очередь", callback_data="queue_refresh")],
        [InlineKeyboardButton("📊 Посмотреть статистику", callback_data="show_stats")],
    ])

    if update.callback_query:
        await update.callback_query.edit_message_text(
            finish_text,
            parse_mode=ParseMode.HTML,
            reply_markup=buttons,
        )
    elif update.message:
        await update.message.reply_text(
            finish_text,
            parse_mode=ParseMode.HTML,
            reply_markup=buttons,
        )


def register_review_handlers(app) -> None:
    app.add_handler(CommandHandler("review", start_review_session))
    app.add_handler(CallbackQueryHandler(start_review_session, pattern="^review_start$"))
    app.add_handler(CallbackQueryHandler(review_reveal_callback, pattern="^review_reveal:"))
    app.add_handler(CallbackQueryHandler(review_rate_callback, pattern="^review_rate:"))
    app.add_handler(CallbackQueryHandler(review_next_step_callback, pattern="^review_next_step$"))
    app.add_handler(CallbackQueryHandler(review_skip_callback, pattern="^review_skip:"))
    app.add_handler(CallbackQueryHandler(review_exit_callback, pattern="^review_exit$"))
