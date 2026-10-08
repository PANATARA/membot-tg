"""
Keyboards module for MemoPlan bot.
"""
from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from memoplan.presets import PRESETS
from memoplan.models import Topic


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard for fast navigation."""
    keyboard = [
        ["📥 Очередь на сегодня", "➕ Новая тема"],
        ["📚 Все темы", "🏆 Долговременная память"],
        ["📊 Статистика", "⚙️ Настройки"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_queue_inline_keyboard(due_count: int) -> InlineKeyboardMarkup:
    """Inline keyboard under Queue screen."""
    buttons = []
    if due_count > 0:
        buttons.append([
            InlineKeyboardButton(
                f"▶️ Начать повторение ({due_count})",
                callback_data="review_start",
            )
        ])
    buttons.append([
        InlineKeyboardButton("🔄 Обновить", callback_data="queue_refresh"),
        InlineKeyboardButton("➕ Добавить тему", callback_data="action_add_topic"),
    ])
    return InlineKeyboardMarkup(buttons)


def get_review_card_keyboard(
    topic_id: int,
    revealed: bool = False,
    notes_available: bool = True,
) -> InlineKeyboardMarkup:
    """Keyboard during an active review session."""
    buttons = []

    if not revealed and notes_available:
        buttons.append([
            InlineKeyboardButton("💡 Показать шпаргалку / заметки", callback_data=f"review_reveal:{topic_id}")
        ])

    # Three outcome buttons
    buttons.append([
        InlineKeyboardButton("🟢 Отлично (+1)", callback_data=f"review_rate:{topic_id}:easy"),
        InlineKeyboardButton("🟡 С трудом", callback_data=f"review_rate:{topic_id}:hard"),
        InlineKeyboardButton("🔴 Забыл (сброс)", callback_data=f"review_rate:{topic_id}:again"),
    ])

    buttons.append([
        InlineKeyboardButton("⏸ Отложить", callback_data=f"review_skip:{topic_id}"),
        InlineKeyboardButton("⏹ Завершить сессию", callback_data="review_exit"),
    ])
    return InlineKeyboardMarkup(buttons)


def get_presets_keyboard(prefix: str = "preset_select") -> InlineKeyboardMarkup:
    """Keyboard to choose a preset grid."""
    buttons = []
    for pid, p in PRESETS.items():
        buttons.append([
            InlineKeyboardButton(
                f"{p.emoji} {p.title} ({p.total_steps} эт.)",
                callback_data=f"{prefix}:{pid}",
            )
        ])
    return InlineKeyboardMarkup(buttons)


def get_skip_notes_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with a skip button when entering notes."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏩ Пропустить (без заметок)", callback_data="notes_skip")],
        [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")],
    ])


def get_cancel_keyboard(callback_data: str = "cancel_action") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data=callback_data)]
    ])


def get_topic_actions_keyboard(
    topic: Topic,
    page: int = 1,
) -> InlineKeyboardMarkup:
    """Action buttons for a single topic view."""
    buttons = []

    # Pause / Resume toggle
    if topic.is_paused:
        buttons.append([
            InlineKeyboardButton("▶️ Возобновить повторение", callback_data=f"topic_toggle_pause:{topic.id}:{page}")
        ])
    elif topic.is_active:
        buttons.append([
            InlineKeyboardButton("⏸ Поставить на паузу", callback_data=f"topic_toggle_pause:{topic.id}:{page}")
        ])

    buttons.append([
        InlineKeyboardButton("✏️ Изменить заметки", callback_data=f"topic_edit_notes:{topic.id}:{page}"),
        InlineKeyboardButton("🗑 Удалить тему", callback_data=f"topic_delete_prompt:{topic.id}:{page}"),
    ])

    buttons.append([
        InlineKeyboardButton("🔙 Назад к списку", callback_data=f"topics_page:{page}")
    ])
    return InlineKeyboardMarkup(buttons)


def get_delete_confirm_keyboard(topic_id: int, page: int = 1) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💥 Да, удалить", callback_data=f"topic_delete_confirmed:{topic_id}:{page}"),
            InlineKeyboardButton("Отмена", callback_data=f"topic_view:{topic_id}:{page}"),
        ]
    ])


def get_topics_pagination_keyboard(
    topics: List[Topic],
    page: int = 1,
    per_page: int = 5,
    filter_status: str = "all",
) -> InlineKeyboardMarkup:
    """List pagination keyboard."""
    total_items = len(topics)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    current_page_topics = topics[start_idx:end_idx]

    buttons = []
    # Buttons for each topic in the page
    for t in current_page_topics:
        status_icon = "🟢" if t.is_active else ("⏸" if t.is_paused else "🏆")
        buttons.append([
            InlineKeyboardButton(
                f"{status_icon} {t.title} [эт. {t.stage}]",
                callback_data=f"topic_view:{t.id}:{page}",
            )
        ])

    # Navigation row
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"topics_page:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"topics_page:{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("➕ Добавить новую тему", callback_data="action_add_topic"),
        InlineKeyboardButton("🔄 Обновить", callback_data=f"topics_page:{page}"),
    ])

    return InlineKeyboardMarkup(buttons)


def get_settings_keyboard(
    sleep_start: int,
    sleep_end: int,
    tz_offset: int,
    notifications_enabled: bool,
    default_preset: str,
) -> InlineKeyboardMarkup:
    """Settings menu keyboard."""
    notif_text = "🔔 Уведомления: Включены" if notifications_enabled else "🔕 Уведомления: Выключены"
    sign = "+" if tz_offset >= 0 else ""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"🌙 Сон: {sleep_start:02d}:00 — {sleep_end:02d}:00 ✏️",
                callback_data="settings_change_sleep",
            )
        ],
        [
            InlineKeyboardButton(
                f"🌍 Часовой пояс: UTC{sign}{tz_offset} ✏️",
                callback_data="settings_change_tz",
            )
        ],
        [
            InlineKeyboardButton(
                f"🎯 Пресет: {default_preset} ✏️",
                callback_data="settings_change_preset",
            )
        ],
        [
            InlineKeyboardButton(
                notif_text,
                callback_data="settings_toggle_notifications",
            )
        ],
        [
            InlineKeyboardButton(
                "🎁 Загрузить примеры тем (Demo)",
                callback_data="settings_load_demo",
            )
        ],
    ])


def get_notification_push_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard attached to periodic notification push."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Начать повторение", callback_data="review_start")],
        [InlineKeyboardButton("📥 Открыть очередь", callback_data="queue_refresh")],
    ])
