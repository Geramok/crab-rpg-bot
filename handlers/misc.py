# -*- coding: utf-8 -*-
import time

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import HELP_TEXT
from keyboards import kb, BACK, misc_kb
from states import Nav

router = Router()


@router.message(Nav.misc, F.text == "🏆 Топ")
async def show_top(message: Message):
    top = database.get_top_players(10)
    text = "🏆 <b>Топ игроков</b>\n\n"
    if not top:
        text += "Пока пусто."
    else:
        for i, p in enumerate(top, 1):
            text += f"{i}. {p['nickname']} — {p['crab_level']} ур. ({p['molts']} линек)\n"
    await message.answer(text, reply_markup=kb([BACK]))


@router.message(Nav.misc, F.text == "❓ Помощь")
async def show_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=kb([BACK]))


@router.message(Nav.misc, F.text == "📈 Статистика")
async def show_stats(message: Message):
    user = database.get_user(message.from_user.id)
    text = (
        f"📈 <b>Статистика за всё время</b>\n\n"
        f"Всего заработано золота: {user['total_earned_gold']}\n"
        f"Всего получено очков ДНК: {user['total_dna_earned']}\n"
        f"Убито существ: {user['kills']}\n"
        f"Убито боссов: {user['boss_kills']}\n"
        f"Линек пройдено: {user['molts']}\n"
        f"Рекорд по пройденному пути: {user['max_meters']} м"
    )
    await message.answer(text, reply_markup=kb([BACK]))


@router.message(Nav.misc, F.text == "🐉 Ивенты")
async def show_events(message: Message, state: FSMContext):
    await state.set_state(Nav.events)
    event = database.get_active_event()
    if not event:
        await message.answer(
            "Сейчас нет активных ивентов с боссами. Загляни позже! 🌊",
            reply_markup=kb([BACK]),
        )
        return

    left = event["ends_at"] - int(time.time())
    hours = max(left, 0) // 3600
    lb = database.get_event_leaderboard(event["id"], 5)
    text = (
        f"🐉 <b>{event['name']}</b>\n\n"
        f"{event['description']}\n\n"
        f"⏳ До конца ивента: ~{hours} ч.\n\n"
        f"<b>Топ по урону:</b>\n"
    )
    if lb:
        for i, row in enumerate(lb, 1):
            u = database.get_user(row["user_id"])
            name = u["nickname"] if u else row["user_id"]
            text += f"{i}. {name} — {row['damage']} урона\n"
    else:
        text += "пока никто не атаковал\n"

    ikb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Атаковать босса", callback_data=f"boss_attack_{event['id']}")
    ]])
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("Действие:", reply_markup=ikb)


@router.callback_query(F.data.startswith("boss_attack_"))
async def boss_attack(call: CallbackQuery):
    from game_logic import get_effective_stats, player_attack

    event_id = int(call.data.split("_")[-1])
    event = database.get_active_event()
    if not event or event["id"] != event_id:
        await call.answer("Ивент уже завершён.", show_alert=True)
        return

    user = database.get_user(call.from_user.id)
    mutations = database.get_mutations(call.from_user.id)
    stones = database.get_stones(call.from_user.id)
    stats = get_effective_stats(user, mutations, stones)
    dmg, is_crit = player_attack(stats)

    database.add_event_damage(event_id, call.from_user.id, dmg)
    crit_txt = " 💥 Крит!" if is_crit else ""
    await call.answer(f"Ты нанёс боссу {dmg} урона!{crit_txt}")
