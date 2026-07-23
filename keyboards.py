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


def shore_choice_kb():
    return kb(["🏖️ Песчаный берег"], ["🪨 Скалистый берег"], ["🌴 Коралловый берег"])


def main_menu_kb():
    return kb(["🗡️ На охоту", "🧬 Мутации", "📋 Меню"])


def hunt_kb(in_hunt: bool):
    if in_hunt:
        return kb(["⚔️ Атака"], ["🏃 Отступить"], [BACK])
    return kb(["🔎 Искать врага"], [BACK])


def mutations_root_kb():
    return kb(["🧬 Линька"], ["🧪 Мутации"], [BACK])


def menu_root_kb():
    return kb(
        ["👤 Профиль", "📊 Характеристики"],
        ["⛏️ Копать", "🎒 Инвентарь"],
        ["🔧 Прочее"],
        [BACK],
    )


def profile_kb():
    return kb(["✏️ Сменить ник", "🛍️ Магазин"], ["🔍 Найти игрока", "🎲 Другие игроки"], [BACK])


def other_profile_kb():
    return kb([BACK])


def misc_kb():
    return kb(["🏆 Топ", "❓ Помощь"], ["📈 Статистика", "🐉 Ивенты"], [BACK])


def confirm_kb(yes_text="✅ Да", no_text="❌ Нет"):
    return kb([yes_text, no_text])


def only_back_kb():
    return kb([BACK])
