"""
Handlers for Settings: sleep hours, timezone, presets, notifications, and demo data.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from memoplan.database import db
from memoplan.presets import PRESETS
from memoplan.ui.formatters import format_settings
from memoplan.ui.keyboards import get_settings_keyboard


async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display settings screen."""
    user = update.effective_user
    if not user:
        return

    settings = db.get_or_create_user(user.id)
    text = format_settings(settings)
    keyboard = get_settings_keyboard(
        sleep_start=settings.sleep_start_hour,
        sleep_end=settings.sleep_end_hour,
        tz_offset=settings.timezone_offset,
        notifications_enabled=settings.notifications_enabled,
        default_preset=settings.default_preset,
    )

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


async def settings_toggle_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle push notifications on/off."""
    query = update.callback_query
    user_id = query.from_user.id
    settings = db.get_or_create_user(user_id)

    settings.notifications_enabled = not settings.notifications_enabled
    db.update_user_settings(settings)

    status_str = "включены" if settings.notifications_enabled else "выключены"
    await query.answer(f"Уведомления {status_str}")
    await settings_handler(update, context)


async def settings_choose_sleep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show options for sleep hours."""
    query = update.callback_query
    await query.answer()

    text = (
        "🌙 <b>Настройка режима сна (Sleep-Aware)</b>\n\n"
        "Выберите интервал вашего обычного сна. Если тема должна созреть ночью, "
        "бот не будет тревожить вас и перенесёт повторение на утренний слот:"
    )

    options = [
        ("22:00 — 07:00 (Ранний подъём)", 22, 7),
        ("23:00 — 08:00 (Оптимальный)", 23, 8),
        ("23:00 — 09:00 (По умолчанию)", 23, 9),
        ("00:00 — 09:00 (Полуночник)", 0, 9),
        ("01:00 — 10:00 (Сова)", 1, 10),
    ]

    buttons = [
        [InlineKeyboardButton(label, callback_data=f"set_sleep_val:{s}:{e}")]
        for label, s, e in options
    ]
    buttons.append([InlineKeyboardButton("🔙 Назад в настройки", callback_data="settings_back")])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def settings_save_sleep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save selected sleep hours."""
    query = update.callback_query
    parts = query.data.split(":")
    start_h = int(parts[1])
    end_h = int(parts[2])

    user_id = query.from_user.id
    settings = db.get_or_create_user(user_id)
    settings.sleep_start_hour = start_h
    settings.sleep_end_hour = end_h
    db.update_user_settings(settings)

    await query.answer("Режим сна сохранён!")
    await settings_handler(update, context)


async def settings_choose_tz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show options for timezone."""
    query = update.callback_query
    await query.answer()

    text = "🌍 <b>Выберите ваш часовой пояс:</b>"
    tz_list = [
        ("UTC+2 (Калининград)", 2),
        ("UTC+3 (Москва / Минск / СПб)", 3),
        ("UTC+4 (Самара / Баку)", 4),
        ("UTC+5 (Екатеринбург / Ташкент)", 5),
        ("UTC+6 (Омск / Алматы)", 6),
        ("UTC+7 (Новосибирск / Красноярск)", 7),
        ("UTC+8 (Иркутск)", 8),
        ("UTC+9 (Якутск)", 9),
        ("UTC+10 (Владивосток)", 10),
        ("UTC+0 (UTC / Лондон)", 0),
    ]

    buttons = [
        [InlineKeyboardButton(label, callback_data=f"set_tz_val:{val}")]
        for label, val in tz_list
    ]
    buttons.append([InlineKeyboardButton("🔙 Назад в настройки", callback_data="settings_back")])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def settings_save_tz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save selected timezone."""
    query = update.callback_query
    val = int(query.data.split(":")[1])
    user_id = query.from_user.id

    settings = db.get_or_create_user(user_id)
    settings.timezone_offset = val
    db.update_user_settings(settings)

    await query.answer("Часовой пояс обновлен!")
    await settings_handler(update, context)


async def settings_choose_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show options for default preset."""
    query = update.callback_query
    await query.answer()

    text = "🎯 <b>Выберите пресет интервалов по умолчанию для новых тем:</b>"
    buttons = [
        [InlineKeyboardButton(f"{p.emoji} {p.title}", callback_data=f"set_preset_val:{pid}")]
        for pid, p in PRESETS.items()
    ]
    buttons.append([InlineKeyboardButton("🔙 Назад в настройки", callback_data="settings_back")])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def settings_save_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save selected default preset."""
    query = update.callback_query
    pid = query.data.split(":")[1]
    user_id = query.from_user.id

    settings = db.get_or_create_user(user_id)
    settings.default_preset = pid
    db.update_user_settings(settings)

    await query.answer("Пресет по умолчанию обновлен!")
    await settings_handler(update, context)


async def settings_load_demo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Load demo topics from settings screen."""
    query = update.callback_query
    user_id = query.from_user.id

    db.create_demo_topics(user_id)
    await query.answer("Демо-темы успешно загружены!", show_alert=True)
    await settings_handler(update, context)


def register_settings_handlers(app) -> None:
    app.add_handler(CommandHandler("settings", settings_handler))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Настройки$"), settings_handler))
    app.add_handler(CallbackQueryHandler(settings_handler, pattern="^settings_back$"))
    app.add_handler(CallbackQueryHandler(settings_toggle_notifications, pattern="^settings_toggle_notifications$"))
    app.add_handler(CallbackQueryHandler(settings_choose_sleep, pattern="^settings_change_sleep$"))
    app.add_handler(CallbackQueryHandler(settings_save_sleep, pattern="^set_sleep_val:"))
    app.add_handler(CallbackQueryHandler(settings_choose_tz, pattern="^settings_change_tz$"))
    app.add_handler(CallbackQueryHandler(settings_save_tz, pattern="^set_tz_val:"))
    app.add_handler(CallbackQueryHandler(settings_choose_preset, pattern="^settings_change_preset$"))
    app.add_handler(CallbackQueryHandler(settings_save_preset, pattern="^set_preset_val:"))
    app.add_handler(CallbackQueryHandler(settings_load_demo, pattern="^settings_load_demo$"))
