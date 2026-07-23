# -*- coding: utf-8 -*-
import time
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import CRABS, SHORES, MUTATION_SLOTS, SPECIAL_MUTATIONS
from game_logic import get_effective_stats, level_up_cost
from keyboards import profile_kb, kb, BACK
from states import Nav

router = Router()

NICK_COOLDOWN_SECONDS = 7 * 24 * 60 * 60


async def show_profile(message: Message):
    user = database.get_user(message.from_user.id)
    mutations = database.get_mutations(message.from_user.id)
    special = database.get_special_mutations(message.from_user.id)

    equipped = [MUTATION_SLOTS[s]["name"] for s, m in mutations.items() if m["equipped"] and m["level"] > 0]
    equipped += [SPECIAL_MUTATIONS[k]["name"] for k, v in special.items() if v["equipped"]]
    equipped_txt = ", ".join(equipped) if equipped else "нет"

    reg_date = datetime.fromtimestamp(user["registered_at"]).strftime("%d.%m.%Y") if user["registered_at"] else "—"

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Ник: {user['nickname']}\n"
        f"Краб: {CRABS[user['crab_type']]['name']}\n"
        f"Берег: {SHORES.get(user['shore'], '—')}\n"
        f"Уровень краба: {user['crab_level']}\n"
        f"Надетые мутации: {equipped_txt}\n"
        f"Пройденный путь (рекорд): {user['max_meters']} м\n"
        f"Баланс золота: {user['gold']} 💰\n"
        f"Очки ДНК: {user['dna_points']} 🧬\n"
        f"Убито существ: {user['kills']}\n"
        f"Убито боссов: {user['boss_kills']}\n"
        f"Раковин наутилуса: {user['nautilus_shells']}\n"
        f"Дата регистрации: {reg_date}"
    )
    await message.answer(text, reply_markup=profile_kb())


async def show_characteristics(message: Message):
    user = database.get_user(message.from_user.id)
    mutations = database.get_mutations(message.from_user.id)
    stones = database.get_stones(message.from_user.id)
    stats = get_effective_stats(user, mutations, stones)
    cost = level_up_cost(user["crab_level"], user["molts"])

    text = (
        f"📊 <b>Характеристики</b>\n\n"
        f"Уровень краба: {user['crab_level']}\n"
        f"⚔️ Урон: {stats['damage']:.1f}\n"
        f"🌊 Уклонение: {stats['evasion']:.1f}%\n"
        f"🍀 Удача: {stats['luck']:.1f}%\n"
        f"🎯 Крит. шанс: {stats['crit_chance']:.1f}%\n"
        f"💥 Крит. урон: {stats['crit_damage']:.1f}%\n"
        f"❤️ Прочность: {stats['max_hp']}\n\n"
        f"💰 Золото: {user['gold']}\n"
        f"Повышение уровня стоит: {cost} 💰"
    )
    ikb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"⬆️ Повысить уровень ({cost} 💰)", callback_data="level_up")
    ]])
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("Действие:", reply_markup=ikb)


@router.callback_query(F.data == "level_up")
async def level_up(call: CallbackQuery, state: FSMContext):
    user = database.get_user(call.from_user.id)
    cost = level_up_cost(user["crab_level"], user["molts"])
    if user["gold"] < cost:
        await call.answer(f"Не хватает золота! Нужно {cost} 💰.", show_alert=True)
        return
    database.update_user(call.from_user.id, gold=user["gold"] - cost, crab_level=user["crab_level"] + 1)
    await call.answer("Уровень повышен!")

    user = database.get_user(call.from_user.id)
    new_cost = level_up_cost(user["crab_level"], user["molts"])
    ikb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"⬆️ Повысить уровень ({new_cost} 💰)", callback_data="level_up")
    ]])
    await call.message.edit_text(
        f"✅ Новый уровень краба: {user['crab_level']}. Золото: {user['gold']} 💰.\n"
        f"Следующий уровень: {new_cost} 💰"
    )
    await call.message.answer("Действие:", reply_markup=ikb)


# ---------------- Смена ника ----------------

@router.message(Nav.profile, F.text == "✏️ Сменить ник")
async def change_nick_request(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    last_change = user["last_nick_change_ts"] or 0
    left = NICK_COOLDOWN_SECONDS - (int(time.time()) - last_change)
    if left > 0:
        days = left // 86400 + 1
        await message.answer(f"Менять ник можно раз в 7 дней. Подожди ещё ~{days} дн.", reply_markup=profile_kb())
        return
    await state.update_data(return_state="profile")
    await state.set_state(Nav.waiting_nickname)
    await message.answer("Введи новый ник (3-16 символов):", reply_markup=kb([BACK]))


@router.message(Nav.waiting_nickname)
async def change_nick_apply(message: Message, state: FSMContext):
    if message.text == BACK:
        await state.set_state(Nav.profile)
        await show_profile(message)
        return
    nick = message.text.strip()
    if not (3 <= len(nick) <= 16):
        await message.answer("Ник должен быть от 3 до 16 символов. Попробуй ещё раз:")
        return
    database.update_user(message.from_user.id, nickname=nick, last_nick_change_ts=int(time.time()))
    await state.set_state(Nav.profile)
    await message.answer(f"Готово! Новый ник: {nick}")
    await show_profile(message)


# ---------------- Магазин (заглушка под реальные платежи) ----------------

@router.message(Nav.profile, F.text == "🛍️ Магазин")
async def open_shop(message: Message, state: FSMContext):
    await state.set_state(Nav.shop)
    user = database.get_user(message.from_user.id)
    text = (
        "🛍️ <b>Магазин</b>\n\n"
        f"🐚 Раковин наутилуса: {user['nautilus_shells']}\n\n"
        "За раковины можно купить:\n"
        "🐟 Золотой скат — разовая порция золота\n"
        "🦐 Синяя креветка — разовая порция очков ДНК\n\n"
        "⚠️ Оплата реальными деньгами пока не подключена (нужна регистрация ИП для приёма платежей). "
        "Как только подключим платёжную систему, здесь появится возможность купить раковины."
    )
    await message.answer(text, reply_markup=kb([BACK]))
