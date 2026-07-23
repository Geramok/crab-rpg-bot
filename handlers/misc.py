# -*- coding: utf-8 -*-
import time

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import (
    HELP_PAGES, MYTHIC_EVENT_UNLOCK_MOLTS, MYTHIC_EVENT_UNLOCK_MAX_METERS, MYTHIC_EVENT_UNLOCK_KILLS,
)
from game_logic import mythic_events_unlocked, get_depth_zone_name
from keyboards import kb, BACK, misc_kb, help_pagination_kb
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
            zone = get_depth_zone_name(p["max_meters"])
            text += f"{i}. {p['nickname']} — {p['crab_level']} ур. ({p['molts']} линек, {zone})\n"
    await message.answer(text, reply_markup=kb([BACK]))


@router.message(Nav.misc, F.text == "❓ Помощь")
async def show_help(message: Message):
    title, text = HELP_PAGES[0]
    await message.answer(f"<b>{title}</b>\n\n{text}", reply_markup=kb([BACK]))
    await message.answer("Листай страницы:", reply_markup=help_pagination_kb(0, len(HELP_PAGES)))


@router.callback_query(F.data.startswith("help_page_"))
async def help_page(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    if not (0 <= page < len(HELP_PAGES)):
        await call.answer()
        return
    title, text = HELP_PAGES[page]
    await call.answer()
    await call.message.edit_text(
        f"<b>{title}</b>\n\n{text}", reply_markup=help_pagination_kb(page, len(HELP_PAGES))
    )


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
        f"Рекорд по пройденному пути: {user['max_meters']} м ({get_depth_zone_name(user['max_meters'])})"
    )
    await message.answer(text, reply_markup=kb([BACK]))


@router.message(Nav.misc, F.text == "🐉 Ивенты")
async def show_events(message: Message, state: FSMContext):
    await state.set_state(Nav.events)
    user = database.get_user(message.from_user.id)

    if not mythic_events_unlocked(user):
        await message.answer(
            f"🐉 Мифические ивенты с боссами открываются, когда выполнишь ЛЮБОЕ из условий:\n\n"
            f"• {MYTHIC_EVENT_UNLOCK_MOLTS}-я линька (у тебя: {user['molts']})\n"
            f"• {MYTHIC_EVENT_UNLOCK_MAX_METERS} м. рекорд по пройденному пути (у тебя: {user['max_meters']})\n"
            f"• {MYTHIC_EVENT_UNLOCK_KILLS} убитых существ (у тебя: {user['kills']})\n\n"
            f"Продолжай играть в удобном тебе стиле — все три пути ведут к ивентам!",
            reply_markup=kb([BACK]),
        )
        return

    event = database.get_active_event()
    if not event:
        await message.answer(
            "Сейчас нет активных ивентов с боссами. Они запускаются автоматически — загляни позже! 🌊",
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
    text += (
        "\n💡 Награды распределяются не только по топу урона — жемчужные кейсы "
        "разыгрываются между всеми активными участниками, шанс есть у каждого!"
    )

    ikb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Атаковать босса", callback_data=f"boss_attack_{event['id']}")
    ]])
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("Действие:", reply_markup=ikb)


@router.callback_query(F.data.startswith("boss_attack_"))
async def boss_attack(call: CallbackQuery):
    from game_logic import get_effective_stats, player_attack

    user = database.get_user(call.from_user.id)
    if not mythic_events_unlocked(user):
        await call.answer("Ивенты пока недоступны — смотри условия в разделе Ивенты.", show_alert=True)
        return

    event_id = int(call.data.split("_")[-1])
    event = database.get_active_event()
    if not event or event["id"] != event_id:
        await call.answer("Ивент уже завершён.", show_alert=True)
        return

    stones = database.get_stones(call.from_user.id)
    mutations = database.get_mutations(call.from_user.id)
    stats = get_effective_stats(user, stones, mutations)
    dmg, is_crit, missed = player_attack(stats)

    if missed:
        await call.answer("💨 Промах!")
        return

    database.add_event_damage(event_id, call.from_user.id, dmg)
    crit_txt = " 💥 Крит!" if is_crit else ""
    await call.answer(f"Ты нанёс боссу {dmg} урона!{crit_txt}")
