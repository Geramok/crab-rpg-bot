# -*- coding: utf-8 -*-
import re
import time
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import CRABS, SPECIAL_MUTATIONS, STAT_LABELS, SHIELD_ABILITY, MARK_ABILITY, UNIQUE_ABILITIES
from game_logic import get_effective_stats, get_mutation_variant, level_up_cost, get_depth_zone_name
from keyboards import profile_kb, kb, BACK, other_profile_kb
from states import Nav

router = Router()

NICK_COOLDOWN_SECONDS = 7 * 24 * 60 * 60
# Ник показывается другим игрокам (топ, поиск, профили) в сообщениях с parse_mode=HTML.
# Разрешаем только буквы/цифры/пробел/_/- — это закрывает HTML-инъекцию через ник
# (иначе кто-то мог бы вписать <b>/<a href=...> и сломать чужие сообщения).
NICKNAME_PATTERN = re.compile(r"^[a-zA-Zа-яА-ЯёЁ0-9 _\-]{3,16}$")


def _equipped_mutation_names(user_id):
    mutations = database.get_mutations(user_id)
    special = database.get_special_mutations(user_id)
    names = []
    for slot, m in mutations.items():
        if m["equipped"] and m["level"] > 0 and m.get("variant_key"):
            variant = get_mutation_variant(slot, m["variant_key"])
            if variant:
                names.append(f"{variant['name']} (ур. {m['level']})")
    names += [SPECIAL_MUTATIONS[k]["name"] for k, v in special.items() if v["equipped"]]
    return names


async def show_profile(message: Message):
    user = database.get_user(message.from_user.id)
    equipped = _equipped_mutation_names(message.from_user.id)
    equipped_txt = ", ".join(equipped) if equipped else "нет"

    reg_date = datetime.fromtimestamp(user["registered_at"]).strftime("%d.%m.%Y") if user["registered_at"] else "—"

    zone = get_depth_zone_name(user["max_meters"])
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Ник: {user['nickname']}\n"
        f"Краб: {CRABS[user['crab_type']]['name']}\n"
        f"Уровень моря: {zone}\n"
        f"Уровень краба: {user['crab_level']}\n"
        f"Линек пройдено: {user['molts']}\n"
        f"Надетые мутации: {equipped_txt}\n"
        f"Пройденный путь (рекорд): {user['max_meters']} м\n"
        f"Баланс золота: {user['gold']} 💰\n"
        f"Очки ДНК: {user['dna_points']} 🧬\n"
        f"Убито существ: {user['kills']}\n"
        f"Убито боссов: {user['boss_kills']}\n"
        f"Раковин наутилуса: {user['nautilus_shells']}\n"
        f"Дата регистрации: {reg_date}"
    )
    if user["permanent_boost"]:
        text += "\n🌟 Вечный прилив: +15% к золоту и ДНК навсегда"
    await message.answer(text, reply_markup=profile_kb())


async def _show_other_profile_text(target_user):
    equipped = _equipped_mutation_names(target_user["user_id"])
    equipped_txt = ", ".join(equipped) if equipped else "нет"
    zone = get_depth_zone_name(target_user["max_meters"])
    text = (
        f"👤 <b>Профиль игрока {target_user['nickname']}</b>\n\n"
        f"Краб: {CRABS[target_user['crab_type']]['name']}\n"
        f"Уровень моря: {zone}\n"
        f"Уровень краба: {target_user['crab_level']}\n"
        f"Линек пройдено: {target_user['molts']}\n"
        f"Мутации: {equipped_txt}\n"
        f"Пройденный путь (рекорд): {target_user['max_meters']} м\n"
        f"Убито существ: {target_user['kills']}\n"
        f"Убито боссов: {target_user['boss_kills']}"
    )
    return text


def _characteristics_text_and_kb(user_id):
    user = database.get_user(user_id)
    stones = database.get_stones(user_id)
    mutations = database.get_mutations(user_id)
    stats = get_effective_stats(user, stones, mutations)
    cost = level_up_cost(user["crab_level"], user["molts"])

    equipped_lines = []
    for slot, m in mutations.items():
        if m["equipped"] and m["level"] > 0 and m.get("variant_key"):
            variant = get_mutation_variant(slot, m["variant_key"])
            if variant:
                buff = variant["buff_per_level"] * m["level"]
                debuff = variant["debuff_per_level"] * m["level"]
                equipped_lines.append(
                    f"{variant['name']} (ур. {m['level']}): +{buff:.1f} {STAT_LABELS[variant['buff_stat']]}, "
                    f"-{debuff:.1f} {STAT_LABELS[variant['debuff_stat']]}"
                )
    mutations_txt = "\n".join(equipped_lines) if equipped_lines else "нет надетых мутаций"

    unique = UNIQUE_ABILITIES.get(user["crab_type"], UNIQUE_ABILITIES[1])
    abilities_txt = (
        f"{SHIELD_ABILITY['name']} — {SHIELD_ABILITY['desc']}\n"
        f"{MARK_ABILITY['name']} — {MARK_ABILITY['desc']}\n"
        f"{unique['name']} (твоя уникальная) — {unique['desc']}"
    )

    text = (
        f"📊 <b>Характеристики</b>\n\n"
        f"Уровень краба: {user['crab_level']}\n"
        f"⚔️ Урон: {stats['damage']:.1f}\n"
        f"🌊 Уклонение: {stats['evasion']:.1f}%\n"
        f"🍀 Удача: {stats['luck']:.1f}%\n"
        f"🎯 Крит. шанс: {stats['crit_chance']:.1f}%\n"
        f"💥 Крит. урон: {stats['crit_damage']:.1f}%\n"
        f"❤️ Прочность: {stats['max_hp']}\n\n"
        f"<b>Надетые мутации-артефакты:</b>\n{mutations_txt}\n\n"
        f"<b>⚡ Боевые способности (кнопки прямо в бою):</b>\n{abilities_txt}\n\n"
        f"💰 Золото: {user['gold']}\n"
        f"Повышение уровня стоит: {cost} 💰"
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
