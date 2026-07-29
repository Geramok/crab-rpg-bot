# -*- coding: utf-8 -*-
import time
from collections import Counter

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import database
from data import STONE_COLORS, RESOURCES, DIG_DURATION_OPTIONS_HOURS
from game_logic import roll_dig_loot, roll_dig_resources
from keyboards import kb, BACK, dig_duration_kb

router = Router()


async def show_dig(message: Message):
    user = await database.run_async(database.get_user, message.from_user.id)
    start_ts = user["dig_start_ts"]
    duration = user["dig_duration_seconds"]
    now = int(time.time())

    if not start_ts:
        text = (
            "⛏️ <b>Копать</b>\n\n"
            "Выбери, сколько времени краб будет копать — чем дольше, тем больше добычи "
            "(линейно, без штрафов и без выгоды от частых коротких копаний).\n"
            "💡 Камни и ресурсы применяются/копятся <b>автоматически</b>, их не нужно "
            "отдельно надевать или использовать."
        )
        await message.answer(text, reply_markup=kb([BACK]))
        await message.answer("Выбери длительность:", reply_markup=dig_duration_kb(DIG_DURATION_OPTIONS_HOURS))
        return

    if now - start_ts < duration:
        left = duration - (now - start_ts)
        mins = left // 60 + 1
        text = f"⛏️ Краб копает дно... Осталось примерно {mins} мин."
        await message.answer(text, reply_markup=kb([BACK]))
        return

    text = "🎁 Копание завершено! Забери добычу."
    ikb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎁 Забрать добычу", callback_data="collect_dig")
    ]])
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("Забрать добычу?", reply_markup=ikb)


@router.callback_query(F.data.startswith("dig_start_"))
async def start_dig(call: CallbackQuery):
    hours = int(call.data.split("_")[-1])
    if hours not in DIG_DURATION_OPTIONS_HOURS:
        await call.answer()
        return
    started = await database.run_async(database.try_start_dig, call.from_user.id, hours * 3600)
    if not started:
        await call.answer("Копание уже идёт.", show_alert=True)
        return
    await call.answer(f"Краб начал копать на {hours} ч.!")
    await call.message.edit_text(f"⛏️ Краб копает дно {hours} ч.... Загляни попозже.")


@router.callback_query(F.data == "collect_dig")
async def collect_dig(call: CallbackQuery):
    user = await database.run_async(database.get_user, call.from_user.id)
    start_ts = user["dig_start_ts"]
    duration = user["dig_duration_seconds"] or 3600
    now = int(time.time())
    if not start_ts or now - start_ts < duration:
        await call.answer("Копание ещё не завершено.", show_alert=True)
        return

    collected = await database.run_async(database.try_collect_dig, call.from_user.id, start_ts)
    if not collected:
        await call.answer("Уже забрано!", show_alert=True)
        return

    hours = duration / 3600
    stone_loot = roll_dig_loot(hours)
    for color, level in stone_loot:
        await database.run_async(database.add_stone, call.from_user.id, color, level, 1)

    resource_loot = roll_dig_resources(hours)
    for key in resource_loot:
        await database.run_async(database.add_resource, call.from_user.id, key, 1)

    lines = ["🎁 <b>Добыча (уже применена/добавлена в инвентарь):</b>"]
    counter = Counter(stone_loot)
    for (color, level), cnt in counter.items():
        lines.append(f"{STONE_COLORS[color]['name']} (ур. {level}) × {cnt}")
    if resource_loot:
        rc = Counter(resource_loot)
        lines.append("")
        for key, cnt in rc.items():
            lines.append(f"{RESOURCES[key]['name']} × {cnt}")

    await call.answer("Добыча получена!")
    await call.message.edit_text("\n".join(lines))
