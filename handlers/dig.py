# -*- coding: utf-8 -*-
import time
from collections import Counter

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import database
from data import DIG_COOLDOWN_SECONDS, STONE_COLORS
from game_logic import roll_dig_loot
from keyboards import kb, BACK

router = Router()


async def show_dig(message: Message):
    user = database.get_user(message.from_user.id)
    start_ts = user["dig_start_ts"]
    now = int(time.time())

    if not start_ts:
        text = "⛏️ <b>Копать</b>\n\nОтправь краба копать дно — через час он принесёт камни, усиливающие характеристики."
        ikb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⛏️ Начать копать", callback_data="start_dig")
        ]])
    elif now - start_ts < DIG_COOLDOWN_SECONDS:
        left = DIG_COOLDOWN_SECONDS - (now - start_ts)
        mins = left // 60 + 1
        text = f"⛏️ Краб копает дно... Осталось примерно {mins} мин."
        ikb = None
    else:
        text = "🎁 Копание завершено! Забери добычу."
        ikb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎁 Забрать добычу", callback_data="collect_dig")
        ]])

    await message.answer(text, reply_markup=kb([BACK]))
    if ikb:
        await message.answer("Действие:", reply_markup=ikb)


@router.callback_query(F.data == "start_dig")
async def start_dig(call: CallbackQuery):
    user = database.get_user(call.from_user.id)
    if user["dig_start_ts"]:
        await call.answer("Копание уже идёт.", show_alert=True)
        return
    database.update_user(call.from_user.id, dig_start_ts=int(time.time()))
    await call.answer("Краб начал копать! Загляни через час.")
    await call.message.edit_text("⛏️ Краб копает дно... Загляни примерно через час.")


@router.callback_query(F.data == "collect_dig")
async def collect_dig(call: CallbackQuery):
    user = database.get_user(call.from_user.id)
    start_ts = user["dig_start_ts"]
    now = int(time.time())
    if not start_ts or now - start_ts < DIG_COOLDOWN_SECONDS:
        await call.answer("Копание ещё не завершено.", show_alert=True)
        return

    loot = roll_dig_loot()
    for color, level in loot:
        database.add_stone(call.from_user.id, color, level, 1)
    database.update_user(call.from_user.id, dig_start_ts=None)

    counter = Counter(loot)
    lines = ["🎁 <b>Добыча:</b>"]
    for (color, level), cnt in counter.items():
        lines.append(f"{STONE_COLORS[color]['name']} (ур. {level}) × {cnt}")
    await call.answer("Добыча получена!")
    await call.message.edit_text("\n".join(lines))
