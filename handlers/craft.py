# -*- coding: utf-8 -*-
import time

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import database
from data import RESOURCES, NECTAR_RECIPE, NECTAR_BUFF_DAMAGE_MULT, NECTAR_BUFF_DURATION_SECONDS
from keyboards import kb, BACK

router = Router()


async def _craft_text_and_kb(user_id):
    resources = await database.run_async(database.get_resources, user_id)
    user = await database.run_async(database.get_user, user_id)

    text = "🍯 <b>Нектар силы</b>\n\n<b>Рецепт:</b>\n"
    for key, need in NECTAR_RECIPE.items():
        have = resources.get(key, 0)
        mark = "✅" if have >= need else "▫️"
        text += f"{mark} {RESOURCES[key]['name']}: {have}/{need}\n"
    text += f"\nЭффект: +{round((NECTAR_BUFF_DAMAGE_MULT - 1) * 100)}% урона на {NECTAR_BUFF_DURATION_SECONDS // 60} мин."

    now = int(time.time())
    if user["buff_expires_ts"] and user["buff_expires_ts"] > now:
        left_min = (user["buff_expires_ts"] - now) // 60 + 1
        text += f"\n\n✨ Бафф уже активен ещё {left_min} мин.!"

    can_craft = all(resources.get(k, 0) >= v for k, v in NECTAR_RECIPE.items())
    buttons = [[InlineKeyboardButton(text="🍯 Скрафтить Нектар", callback_data="craft_nectar")]] if can_craft else []
    if not buttons:
        buttons = [[InlineKeyboardButton(text="🍯 Скрафтить Нектар (не хватает ресурсов)", callback_data="craft_nectar")]]
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_craft(message: Message):
    text, ikb = await _craft_text_and_kb(message.from_user.id)
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("Готов скрафтить?", reply_markup=ikb)


@router.callback_query(F.data == "craft_nectar")
async def craft_nectar(call: CallbackQuery):
    crafted = await database.run_async(database.try_craft, call.from_user.id, NECTAR_RECIPE)
    if not crafted:
        await call.answer("Не хватает ресурсов для крафта.", show_alert=True)
        return

    expires = int(time.time()) + NECTAR_BUFF_DURATION_SECONDS
    await database.run_async(
        database.update_user,
        call.from_user.id,
        buff_damage_mult=NECTAR_BUFF_DAMAGE_MULT,
        buff_expires_ts=expires,
    )
    await call.answer("Нектар силы использован! Бафф активен.")
    text, ikb = await _craft_text_and_kb(call.from_user.id)
    await call.message.edit_text(text, reply_markup=ikb)
