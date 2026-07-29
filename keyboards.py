# -*- coding: utf-8 -*-
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

BACK = "⬅️ Назад"


def kb(*rows, resize=True):
    keyboard = [[KeyboardButton(text=t) for t in row] for row in rows]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=resize)


def intro_kb():
    return kb(["📖 Обучение", "▶️ Начать игру"])


def crab_choice_kb():
    return kb(["🦀 Панцирник"], ["🦞 Быстроход"], ["🦐 Крит-краб"])


def main_menu_kb():
    return kb(["🔎 Рыскать по дну", "🧬 Мутации", "📋 Меню"])


def hunt_kb(in_hunt: bool):
    if in_hunt:
        return kb(["↩️ Бочком назад"])
    return kb(["🔎 Рыскать по дну"], [BACK])


def mutations_root_kb():
    return kb(["🧬 Линька"], ["🧪 Мутации"], [BACK])


def menu_root_kb():
    return kb(
        ["🦀 Мой краб", "⚔️ Мощь"],
        ["⛏️ Копать", "🐚 Нора"],
        ["🍯 Нектар", "🔧 Прочее"],
        [BACK],
    )


def profile_kb():
    return kb(["✏️ Сменить ник", "🛍️ Магазин"], ["🔍 Найти игрока", "🎲 Другие игроки"], [BACK])


def other_profile_kb():
    return kb([BACK])


def misc_kb():
    return kb(["🏆 Топ", "❓ Помощь"], ["📈 Статистика", "🐉 Ивенты"], [BACK])


def dig_duration_kb(options_hours):
    buttons = [[InlineKeyboardButton(text=f"⛏️ {h} ч.", callback_data=f"dig_start_{h}")] for h in options_hours]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def help_pagination_kb(page, total_pages):
    buttons = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"help_page_{page-1}"))
    if page < total_pages - 1:
        row.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"help_page_{page+1}"))
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_kb(yes_text="✅ Да", no_text="❌ Нет"):
    return kb([yes_text, no_text])


def only_back_kb():
    return kb([BACK])
