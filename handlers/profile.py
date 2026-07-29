# -*- coding: utf-8 -*-
import re
import time

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import CRABS, SPECIAL_MUTATIONS, SHIELD_ABILITY, MARK_ABILITY, UNIQUE_ABILITIES
from game_logic import get_effective_stats, get_mutation_variant, level_up_cost, get_depth_zone_name, get_molt_rank
from keyboards import profile_kb, kb, BACK, other_profile_kb
from states import Nav

router = Router()

NICK_COOLDOWN_SECONDS = 7 * 24 * 60 * 60
# Ник показывается другим игрокам (топ, поиск, профили) в сообщениях с parse_mode=HTML.
# Разрешаем только буквы/цифры/пробел/_/- — это закрывает HTML-инъекцию через ник
# (иначе кто-то мог бы вписать <b>/<a href=...> и сломать чужие сообщения).
NICKNAME_PATTERN = re.compile(r"^[a-zA-Zа-яА-ЯёЁ0-9 _\-]{3,16}$")


async def show_profile(message: Message):
    user = database.get_user(message.from_user.id)
    zone = get_depth_zone_name(user["max_meters"])
    rank = get_molt_rank(user["molts"])

    text = (
        f"🦀 <b>{user['nickname']}</b> — {rank}\n"
        f"{CRABS[user['crab_type']]['name']} · ур. {user['crab_level']} · {user['molts']} линек\n\n"
        f"📍 {zone} (рекорд {user['max_meters']} м)\n"
        f"💰 {user['gold']}  🧬 {user['dna_points']}  🐚 {user['nautilus_shells']}\n"
        f"Убито: {user['kills']} (боссов: {user['boss_kills']})"
    )
    if user["permanent_boost"]:
        text += "\n🌟 Вечный прилив: +15% к золоту и ДНК навсегда"
    await message.answer(text, reply_markup=profile_kb())


async def _show_other_profile_text(target_user):
    zone = get_depth_zone_name(target_user["max_meters"])
    rank = get_molt_rank(target_user["molts"])
    text = (
        f"🦀 <b>{target_user['nickname']}</b> — {rank}\n"
        f"{CRABS[target_user['crab_type']]['name']} · ур. {target_user['crab_level']} · {target_user['molts']} линек\n\n"
        f"📍 {zone} (рекорд {target_user['max_meters']} м)\n"
        f"Убито: {target_user['kills']} (боссов: {target_user['boss_kills']})"
    )
    return text


def _characteristics_text_and_kb(user_id):
    user = database.get_user(user_id)
    stones = database.get_stones(user_id)
    mutations = database.get_mutations(user_id)
    stats = get_effective_stats(user, stones, mutations)
    cost = level_up_cost(user["crab_level"], user["molts"])

    mutation_names = []
    for slot, m in mutations.items():
        if m["equipped"] and m["level"] > 0 and m.get("variant_key"):
            variant = get_mutation_variant(slot, m["variant_key"])
            if variant:
                mutation_names.append(f"{variant['name']} ({m['level']})")
    special = database.get_special_mutations(user_id)
    mutation_names += [SPECIAL_MUTATIONS[k]["name"] for k, v in special.items() if v["equipped"]]
    mutations_txt = ", ".join(mutation_names) if mutation_names else "нет"

    unique = UNIQUE_ABILITIES.get(user["crab_type"], UNIQUE_ABILITIES[1])
    abilities_txt = f"{SHIELD_ABILITY['name']}, {MARK_ABILITY['name']}"

    text = (
        f"⚔️ <b>Мощь</b> — ур. {user['crab_level']}\n\n"
        f"⚔️{stats['damage']:.1f} 🌊{stats['evasion']:.0f}% 🍀{stats['luck']:.0f}% "
        f"🎯{stats['crit_chance']:.0f}% 💥{stats['crit_damage']:.0f}% ❤️{stats['max_hp']:.0f}\n\n"
        f"Мутации: {mutations_txt}\n"
        f"Способности: {abilities_txt}\n"
        f"Твоя уникальная: {unique['name']} — {unique['desc']}\n\n"
        f"💰 {user['gold']} · след. уровень: {cost} 💰"
    )
    ikb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"⬆️ Повысить уровень ({cost} 💰)", callback_data="level_up")
    ]])
    return text, ikb


async def show_characteristics(message: Message):
    text, ikb = _characteristics_text_and_kb(message.from_user.id)
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("Повысить уровень?", reply_markup=ikb)


@router.callback_query(F.data == "level_up")
async def level_up(call: CallbackQuery, state: FSMContext):
    user = database.get_user(call.from_user.id)
    cost = level_up_cost(user["crab_level"], user["molts"])
    if user["gold"] < cost:
        await call.answer(f"Не хватает золота! Нужно {cost} 💰.", show_alert=True)
        return

    spent = database.try_spend(call.from_user.id, "gold", cost)
    if not spent:
        await call.answer("Не успел — баланс уже изменился, попробуй ещё раз.", show_alert=True)
        return
    database.update_user(call.from_user.id, crab_level=user["crab_level"] + 1)
    await call.answer("Уровень повышен!")

    # редактируем ТО ЖЕ сообщение с полной актуальной сводкой характеристик —
    # видно "изменено" вместо нового сообщения в чате
    text, ikb = _characteristics_text_and_kb(call.from_user.id)
    await call.message.edit_text(f"✅ Уровень повышен!\n\n{text}", reply_markup=ikb)


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
    await state.set_state(Nav.waiting_nickname)
    await message.answer("Введи новый ник (3-16 символов):", reply_markup=kb([BACK]))


@router.message(Nav.waiting_nickname)
async def change_nick_apply(message: Message, state: FSMContext):
    if message.text == BACK:
        await state.set_state(Nav.profile)
        await show_profile(message)
        return
    nick = message.text.strip()
    if not NICKNAME_PATTERN.match(nick):
        await message.answer(
            "Ник должен быть от 3 до 16 символов: буквы, цифры, пробел, _ или -. "
            "Символы вроде < > & использовать нельзя. Попробуй ещё раз:"
        )
        return
    database.update_user(message.from_user.id, nickname=nick, last_nick_change_ts=int(time.time()))
    await state.set_state(Nav.profile)
    await message.answer(f"Готово! Новый ник: {nick}")
    await show_profile(message)


# ---------------- Магазин (реальные платежи через Telegram Stars) ----------------

@router.message(Nav.profile, F.text == "🛍️ Магазин")
async def open_shop_entry(message: Message, state: FSMContext):
    from handlers.shop import open_shop
    await open_shop(message, state)


# ---------------- Поиск игрока по нику ----------------

@router.message(Nav.profile, F.text == "🔍 Найти игрока")
async def search_player_request(message: Message, state: FSMContext):
    await state.set_state(Nav.waiting_search)
    await message.answer("Введи ник игрока, которого хочешь найти:", reply_markup=kb([BACK]))


@router.message(Nav.waiting_search)
async def search_player_apply(message: Message, state: FSMContext):
    if message.text == BACK:
        await state.set_state(Nav.profile)
        await show_profile(message)
        return
    target = database.find_user_by_nickname(message.text.strip())
    if not target:
        await message.answer("Игрок с таким ником не найден. Попробуй другой ник:")
        return
    text = await _show_other_profile_text(target)
    await state.set_state(Nav.profile)
    await message.answer(text, reply_markup=other_profile_kb())


# ---------------- Случайные игроки для просмотра профиля ----------------

@router.message(Nav.profile, F.text == "🎲 Другие игроки")
async def suggest_players(message: Message, state: FSMContext):
    players = database.get_random_players(message.from_user.id, limit=4)
    if not players:
        await message.answer("Пока в игре больше никого нет — приглашай друзей! 🦀", reply_markup=profile_kb())
        return
    buttons = [[InlineKeyboardButton(
        text=f"{p['nickname']} (ур. {p['crab_level']}, {p['molts']} линек)",
        callback_data=f"view_profile_{p['user_id']}",
    )] for p in players]
    await message.answer(
        "🎲 Вот несколько игроков — можешь глянуть их профиль:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("view_profile_"))
async def view_profile_callback(call: CallbackQuery, state: FSMContext):
    target_id = int(call.data.split("_")[-1])
    target = database.get_user(target_id)
    if not target:
        await call.answer("Этот игрок пропал из базы.", show_alert=True)
        return
    text = await _show_other_profile_text(target)
    await call.answer()
    await call.message.answer(text)
