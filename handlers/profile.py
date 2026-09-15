# -*- coding: utf-8 -*-
import re
import time
import json

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import CRABS, SHIELD_ABILITY, MARK_ABILITY, UNIQUE_ABILITIES, EVOLUTION_NODES, PASSIVE_MUTATIONS, ACTIVE_MUTATIONS
from game_logic import get_effective_stats, level_up_cost, get_depth_zone_name, get_molt_rank, format_number
from keyboards import profile_kb, kb, BACK, other_profile_kb
from states import Nav

router = Router()

NICK_COOLDOWN_SECONDS = 7 * 24 * 60 * 60
NICKNAME_PATTERN = re.compile(r"^[a-zA-Zа-яА-ЯёЁ0-9 _\-]{3,16}$")

async def show_profile(message: Message):
    user = await database.run_async(database.get_user, message.from_user.id)
    zone = get_depth_zone_name(user["max_meters"])
    rank = get_molt_rank(user["molts"])

    text = (
        f"🦀 <b>{user['nickname']}</b> — {rank}\n"
        f"{CRABS[user['crab_type']]['name']} · ур. {user['crab_level']} · {user['molts']} линек\n\n"
        f"📍 {zone} (рекорд {user['max_meters']} м)\n"
        f"💰 {format_number(user['gold'])}  🧬 {format_number(user['dna_points'])}  🐚 {format_number(user['nautilus_shells'])}\n"
        f"Убито: {format_number(user['kills'])} (боссов: {user['boss_kills']})"
    )
    if user["permanent_boost"]:
        text += "\n🌟 Вечный прилив: +15% к золоту и ДНК навсегда"
    await message.answer(text, reply_markup=profile_kb())

async def _show_other_profile_text(target_user):
    zone = get_depth_zone_name(target_user["max_meters"])
    rank = get_molt_rank(target_user["molts"])
    
    stones = await database.run_async(database.get_stones, target_user["user_id"])
    mutations = await database.run_async(database.get_user_mutations_v3, target_user["user_id"])
    stats = get_effective_stats(target_user, stones, mutations)
    
    mutation_names = []
    for m in mutations:
        if m["is_active"] == 1 and m["equipped"] == 1:
            variant = ACTIVE_MUTATIONS.get(m["variant_key"])
            if variant: mutation_names.append(f"🌟 {variant['name']}")
                    
    mutations_txt = ", ".join(mutation_names) if mutation_names else "нет"
    
    text = (
        f"🦀 <b>{target_user['nickname']}</b> — {rank}\n"
        f"{CRABS[target_user['crab_type']]['name']} · ур. {target_user['crab_level']} · {target_user['molts']} линек\n\n"
        f"📍 {zone} (рекорд {target_user['max_meters']} м)\n"
        f"⚔️ Урон: {stats['damage']:.1f} | ❤️ Макс. ХП: {format_number(int(stats['max_hp']))}\n"
        f"🧬 Экипировано: {mutations_txt}\n\n"
        f"Убито: {format_number(target_user['kills'])} (боссов: {target_user['boss_kills']})"
    )
    return text

def _calc_max_levels(current_level, molts, gold):
    max_levels = 0
    total_cost = 0
    curr_lvl = current_level
    for _ in range(5000):
        c = level_up_cost(curr_lvl, molts)
        if gold >= total_cost + c:
            total_cost += c
            max_levels += 1
            curr_lvl += 1
        else: break
    return max_levels, total_cost

async def _characteristics_text_and_kb(user_id):
    user = await database.run_async(database.get_user, user_id)
    stones = await database.run_async(database.get_stones, user_id)
    mutations = await database.run_async(database.get_user_mutations_v3, user_id)
    stats = get_effective_stats(user, stones, mutations)
    
    cost_one = level_up_cost(user["crab_level"], user["molts"])
    max_levels, total_cost = _calc_max_levels(user["crab_level"], user["molts"], user["gold"])

    mutation_names = []
    passive_count = sum(1 for m in mutations if m["is_active"] == 0)
    for m in mutations:
        if m["is_active"] == 1 and m["equipped"] == 1:
            variant = ACTIVE_MUTATIONS.get(m["variant_key"])
            if variant: mutation_names.append(f"{variant['name']} ({m['level']})")
                    
    mutations_txt = ", ".join(mutation_names) if mutation_names else "нет"

    unique = UNIQUE_ABILITIES.get(user["crab_type"], UNIQUE_ABILITIES[1])
    abilities_txt = f"{SHIELD_ABILITY['name']}, {MARK_ABILITY['name']}"
    
    stage = user.get("evolution_stage", 0)
    available_evo_points = min(10, user["crab_level"] // 50) - stage

    text = (
        f"⚔️ <b>Мощь</b> — ур. {user['crab_level']}\n\n"
        f"⚔️{stats['damage']:.1f} 🌊{stats['evasion']:.0f}% 🍀{stats['luck']:.0f}% "
        f"🎯{stats['crit_chance']:.0f}% 💥{stats['crit_damage']:.0f}% ❤️{format_number(int(stats['max_hp']))}\n\n"
        f"🧬 Пассивных мутаций: {passive_count}/27\n"
        f"🌟 Экипировано: {mutations_txt}\n\n"
        f"Способности: {abilities_txt}\n"
        f"Твоя уникальная: {unique['name']} — {unique['desc']}\n\n"
        f"💰 Твой баланс: {format_number(user['gold'])} 💰"
    )
    
    max_btn_text = f"⬆️ Макс: +{max_levels} ур. ({format_number(total_cost)} 💰)" if max_levels > 0 else "⬆️ Макс. прокачка"
    
    buttons = [
        [InlineKeyboardButton(text=f"⬆️ +1 ур. ({format_number(cost_one)} 💰)", callback_data="level_up")],
        [InlineKeyboardButton(text=max_btn_text, callback_data="level_up_max")]
    ]
    
    if available_evo_points > 0:
        buttons.insert(0, [InlineKeyboardButton(text=f"🌟 Доступна эволюция! ({available_evo_points})", callback_data="open_evo_menu")])
        
    ikb = InlineKeyboardMarkup(inline_keyboard=buttons)
    return text, ikb

async def show_characteristics(message: Message):
    text, ikb = await _characteristics_text_and_kb(message.from_user.id)
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("Повысить уровень?", reply_markup=ikb)

# --- БЛОК ЭВОЛЮЦИИ ---
@router.callback_query(F.data == "open_evo_menu")
async def open_evo_menu(call: CallbackQuery):
    user = await database.run_async(database.get_user, call.from_user.id)
    stage = user.get("evolution_stage", 0)
    available = min(10, user["crab_level"] // 50) - stage
    
    if available <= 0:
        await call.answer("Нет доступных очков эволюции!", show_alert=True)
        return
        
    try: tree = json.loads(user.get("evolution_tree", "[]"))
    except: tree = []
        
    crystal = CRABS[user["crab_type"]]["crystal"]
    
    # Ищем доступные узлы для твоего кристалла, которые ты еще не взял
    options = []
    for key, node in EVOLUTION_NODES.items():
        if key.startswith(crystal) and key not in tree:
            options.append((key, node))
            
    if not options:
        await call.answer("Ты уже открыл все доступные эволюции для этого класса!", show_alert=True)
        return
        
    text = f"🌟 <b>ВЫБОР ЭВОЛЮЦИИ (Этап {stage + 1}/10)</b>\n\nВыбери путь развития. Этот бонус останется с тобой до следующей линьки!"
    buttons = []
    
    # Показываем до 3 вариантов
    for key, node in options[:3]:
        buttons.append([InlineKeyboardButton(text=f"{node['name']} ({node['desc']})", callback_data=f"pick_evo_{key}")])
        
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh_char_menu")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()

@router.callback_query(F.data.startswith("pick_evo_"))
async def pick_evo(call: CallbackQuery):
    key = call.data.replace("pick_evo_", "")
    user = await database.run_async(database.get_user, call.from_user.id)
    stage = user.get("evolution_stage", 0)
    
    if min(10, user["crab_level"] // 50) - stage <= 0:
        await call.answer("Ошибка: нет очков эволюции.", show_alert=True)
        return
        
    await database.run_async(database.update_evolution_tree, call.from_user.id, stage + 1, key)
    await call.answer("🌟 Эволюция завершена! Характеристики увеличены.", show_alert=True)
    
    text, ikb = await _characteristics_text_and_kb(call.from_user.id)
    await call.message.edit_text(text, reply_markup=ikb)

@router.callback_query(F.data == "refresh_char_menu")
async def refresh_char_menu(call: CallbackQuery):
    text, ikb = await _characteristics_text_and_kb(call.from_user.id)
    await call.message.edit_text(text, reply_markup=ikb)
    await call.answer()
# --------------------

@router.callback_query(F.data == "level_up")
async def level_up(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    user = await database.run_async(database.get_user, user_id)
    cost = level_up_cost(user["crab_level"], user["molts"])
    
    if user["gold"] < cost:
        await call.answer(f"Не хватает золота! Нужно {format_number(cost)} 💰.", show_alert=True)
        return

    spent = await database.run_async(database.try_spend, user_id, "gold", cost)
    if not spent:
        await call.answer("Не успел — баланс уже изменился, попробуй ещё раз.", show_alert=True)
        return
        
    await call.answer("Уровень повышен! Здоровье восстановлено.")
    await database.run_async(database.update_user, user_id, crab_level=user["crab_level"] + 1)
    
    user_updated = await database.run_async(database.get_user, user_id)
    stones = await database.run_async(database.get_stones, user_id)
    mutations = await database.run_async(database.get_user_mutations_v3, user_id)
    new_stats = get_effective_stats(user_updated, stones, mutations)
    
    await database.run_async(database.update_user, user_id, cur_hp=new_stats["max_hp"], last_hp_regen_ts=int(time.time()))
    text, ikb = await _characteristics_text_and_kb(user_id)
    await call.message.edit_text(f"✅ Уровень повышен на +1! Панцирь полностью восстановлен.\n\n{text}", reply_markup=ikb)

@router.callback_query(F.data == "level_up_max")
async def level_up_max(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    user = await database.run_async(database.get_user, user_id)
    max_levels, total_cost = _calc_max_levels(user["crab_level"], user["molts"], user["gold"])
    
    if max_levels == 0:
        cost_one = level_up_cost(user["crab_level"], user["molts"])
        await call.answer(f"Не хватает золота! Нужно {format_number(cost_one)} 💰 хотя бы на один уровень.", show_alert=True)
        return

    spent = await database.run_async(database.try_spend, user_id, "gold", total_cost)
    if not spent:
        await call.answer("Не удалось списать золото, баланс изменился. Попробуй ещё раз.", show_alert=True)
        return
        
    await call.answer(f"Уровень повышен на {max_levels}! Здоровье восстановлено.")
    await database.run_async(database.update_user, user_id, crab_level=user["crab_level"] + max_levels)
    
    user_updated = await database.run_async(database.get_user, user_id)
    stones = await database.run_async(database.get_stones, user_id)
    mutations = await database.run_async(database.get_user_mutations_v3, user_id)
    new_stats = get_effective_stats(user_updated, stones, mutations)
    
    await database.run_async(database.update_user, user_id, cur_hp=new_stats["max_hp"], last_hp_regen_ts=int(time.time()))
    text, ikb = await _characteristics_text_and_kb(user_id)
    await call.message.edit_text(f"✅ Уровень повышен на +{max_levels}! Панцирь полностью восстановлен.\n\n{text}", reply_markup=ikb)

# --- (Здесь остальной код смены ника, магазина и поиска игроков остается без изменений) ---
@router.message(Nav.profile, F.text == "✏️ Сменить ник")
async def change_nick_request(message: Message, state: FSMContext):
    user = await database.run_async(database.get_user, message.from_user.id)
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
        await message.answer("Ник должен быть от 3 до 16 символов: буквы, цифры, пробел, _ или -. Символы вроде < > & использовать нельзя. Попробуй ещё раз:")
        return
    await database.run_async(database.update_user, message.from_user.id, nickname=nick, last_nick_change_ts=int(time.time()))
    await state.set_state(Nav.profile)
    await message.answer(f"Готово! Новый ник: {nick}")
    await show_profile(message)

@router.message(Nav.profile, F.text == "🛍️ Магазин")
async def open_shop_entry(message: Message, state: FSMContext):
    from handlers.shop import open_shop
    await open_shop(message, state)

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
    target = await database.run_async(database.find_user_by_nickname, message.text.strip())
    if not target:
        await message.answer("Игрок с таким ником не найден. Попробуй другой ник:")
        return
    text = await _show_other_profile_text(target)
    await state.set_state(Nav.profile)
    await message.answer(text, reply_markup=other_profile_kb())

@router.message(Nav.profile, F.text == "🎲 Другие игроки")
async def suggest_players(message: Message, state: FSMContext):
    players = await database.run_async(database.get_random_players, message.from_user.id, limit=4)
    if not players:
        await message.answer("Пока в игре больше никого нет — приглашай друзей! 🦀", reply_markup=profile_kb())
        return
    buttons = [[InlineKeyboardButton(text=f"{p['nickname']} (ур. {p['crab_level']}, {p['molts']} линек)", callback_data=f"view_profile_{p['user_id']}")] for p in players]
    await message.answer("🎲 Вот несколько игроков — можешь глянуть их профиль:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("view_profile_"))
async def view_profile_callback(call: CallbackQuery, state: FSMContext):
    target_id = int(call.data.split("_")[-1])
    target = await database.run_async(database.get_user, target_id)
    if not target:
        await call.answer("Этот игрок пропал из базы.", show_alert=True)
        return
    text = await _show_other_profile_text(target)
    await call.answer()
    await call.message.answer(text)
