# -*- coding: utf-8 -*-
import random

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import MUTATION_SLOT_NAMES, STAT_LABELS, PASSIVE_MUTATIONS, ACTIVE_MUTATIONS, STONE_COLORS
from game_logic import (
    can_molt, calculate_dna_reward, get_mutation_cost, cost_upgrade_mutation,
    apply_permanent_boost, format_number, roll_chest_loot, MOLT_UNLOCK_LEVEL
)
from keyboards import mutations_root_kb, kb, BACK
from states import Nav

router = Router()

# Для пагинации зафиксируем ключи пассивных мутаций в список
PASSIVE_KEYS = list(PASSIVE_MUTATIONS.keys())

def _molt_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, сбросить панцирь", callback_data="molt_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="molt_cancel"),
    ]])

@router.message(Nav.mutations_root, F.text == "🧬 Линька")
async def molt_request(message: Message, state: FSMContext):
    user = await database.run_async(database.get_user, message.from_user.id)
    
    if not can_molt(user["crab_level"]):
        await message.answer(f"Линька доступна строго с {MOLT_UNLOCK_LEVEL} уровня краба.\nТвой текущий уровень: {user['crab_level']}.", reply_markup=mutations_root_kb())
        return

    gain = apply_permanent_boost(calculate_dna_reward(user["crab_level"]), user)
    
    await message.answer(
        f"⚠️ Линька сбросит твой уровень краба ({user['crab_level']} → 1), эволюцию и золото ({format_number(user['gold'])} 💰).\n"
        f"Взамен ты получишь <b>{format_number(gain)}</b> очков ДНК 🧬\n\nПровести линьку?",
        reply_markup=_molt_confirm_kb(),
    )

@router.callback_query(F.data == "molt_confirm")
async def molt_confirm(call: CallbackQuery, state: FSMContext):
    user = await database.run_async(database.get_user, call.from_user.id)
    if not can_molt(user["crab_level"]):
        await call.answer("Условие для линьки больше не выполняется.", show_alert=True)
        return

    gain = apply_permanent_boost(calculate_dna_reward(user["crab_level"]), user)
    
    await database.run_async(
        database.update_user, call.from_user.id,
        crab_level=1, gold=0, dna_points=user["dna_points"] + gain,
        molts=user["molts"] + 1, total_dna_earned=user["total_dna_earned"] + gain,
        cur_meters=1, evolution_stage=0, evolution_tree="[]" # СБРОС ЭВОЛЮЦИИ
    )
    
    await call.message.edit_text(f"🧬 Линька прошла успешно! Получено <b>{format_number(gain)}</b> ДНК.")
    await call.answer()
    from handlers.start import prompt_crab_choice
    await prompt_crab_choice(call.message, state)

@router.callback_query(F.data == "molt_cancel")
async def molt_cancel(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Линька отменена.")
    await call.answer()

# ---------------- МАГАЗИН И ИНВЕНТАРЬ ----------------
async def _shop_menu(user_id):
    user = await database.run_async(database.get_user, user_id)
    purchased_count = user.get("purchased_mutations", 0)
    new_cost = get_mutation_cost(purchased_count)
    
    text = (
        f"🧪 <b>Лаборатория Мутаций</b>\n\n"
        f"Очки ДНК: <b>{format_number(user['dna_points'])} 🧬</b>\n\n"
        f"<i>Здесь ты можешь купить новые пассивные кристальные мутации. Они работают из инвентаря.</i>"
    )
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🧬 Открыть новую ({format_number(new_cost)})", callback_data="buy_new_mut")],
        [
            InlineKeyboardButton(text="🎒 Пассивные (27)", callback_data="open_passives_0"),
            InlineKeyboardButton(text="⚔️ Активные", callback_data="open_actives")
        ]
    ])
    return text, ikb

@router.message(Nav.mutations_root, F.text == "🧪 Мутации")
async def open_mutations_shop(message: Message, state: FSMContext):
    await state.set_state(Nav.mutations_shop)
    text, ikb = await _shop_menu(message.from_user.id)
    await message.answer("🧬 Открываю лабораторию...", reply_markup=kb([BACK]))
    await message.answer(text, reply_markup=ikb)

@router.callback_query(F.data == "buy_new_mut")
async def buy_new_mut(call: CallbackQuery):
    user = await database.run_async(database.get_user, call.from_user.id)
    owned = await database.run_async(database.get_user_mutations_v3, call.from_user.id)
    owned_keys = [m["variant_key"] for m in owned if m["is_active"] == 0]

    all_possible = [{"key": k, "name": v["name"]} for k, v in PASSIVE_MUTATIONS.items() if k not in owned_keys]

    if not all_possible:
        await call.answer("У тебя уже есть все пассивные мутации из лаборатории!", show_alert=True)
        return

    purchased_count = user.get("purchased_mutations", 0)
    cost = get_mutation_cost(purchased_count)
    
    if user["dna_points"] < cost:
        await call.answer(f"Не хватает ДНК! Нужно {format_number(cost)} 🧬", show_alert=True)
        return

    spent = await database.run_async(database.try_spend, call.from_user.id, "dna_points", cost)
    if spent:
        new_mut = random.choice(all_possible)
        await database.run_async(database.add_new_mutation_v3, call.from_user.id, new_mut["key"], is_active=0)
        await database.run_async(database.update_user, call.from_user.id, purchased_mutations=purchased_count + 1)
        
        await call.answer(f"🎉 ПРОРЫВ!\nВыбита пассивка:\n{new_mut['name']}!", show_alert=True)
        text, ikb = await _shop_menu(call.from_user.id)
        await call.message.edit_text(text, reply_markup=ikb)

# --- ПАГИНАЦИЯ ПАССИВНЫХ МУТАЦИЙ ---
@router.callback_query(F.data.startswith("open_passives_"))
async def open_passives_page(call: CallbackQuery, state: FSMContext):
    await state.set_state(Nav.mutations_inventory)
    page = int(call.data.replace("open_passives_", ""))
    
    owned = await database.run_async(database.get_user_mutations_v3, call.from_user.id)
    owned_dict = {m["variant_key"]: m["level"] for m in owned if m["is_active"] == 0}
    
    start_idx = page * 9
    end_idx = start_idx + 9
    current_keys = PASSIVE_KEYS[start_idx:end_idx]
    
    text = f"🎒 <b>Книга мутаций (Стр. {page+1}/3)</b>\n\n<i>Синергия зависит от твоего класса!</i>"
    buttons = []
    
    for key in current_keys:
        if key in owned_dict:
            lvl = owned_dict[key]
            name = PASSIVE_MUTATIONS[key]["name"]
            buttons.append([InlineKeyboardButton(text=f"[Ур. {lvl}] {name}", callback_data=f"mut_pass_det_{key}_{page}")])
        else:
            buttons.append([InlineKeyboardButton(text="❓ Неизвестная мутация", callback_data="mut_unknown")])
            
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️ Пред", callback_data=f"open_passives_{page-1}"))
    if end_idx < len(PASSIVE_KEYS): nav_row.append(InlineKeyboardButton(text="След ➡️", callback_data=f"open_passives_{page+1}"))
    if nav_row: buttons.append(nav_row)
        
    buttons.append([InlineKeyboardButton(text="🏠 Назад в меню", callback_data="back_to_mut_shop")])
    
    try: await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except: 
        await call.message.delete()
        await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()

@router.callback_query(F.data == "mut_unknown")
async def mut_unknown(call: CallbackQuery):
    await call.answer("❓ Открой эту мутацию в лаборатории за ДНК!", show_alert=True)

# --- АКТИВНЫЕ МУТАЦИИ (ЭКИПИРОВКА) ---
@router.callback_query(F.data == "open_actives")
async def open_actives(call: CallbackQuery, state: FSMContext):
    await state.set_state(Nav.mutations_inventory)
    owned = await database.run_async(database.get_user_mutations_v3, call.from_user.id)
    actives = [m for m in owned if m["is_active"] == 1]
    
    text = "⚔️ <b>Ивентовые мутации (Экипировка)</b>\n\n🟢 — надето\n🔵 — в сумке"
    buttons = []
    for m in actives:
        variant = ACTIVE_MUTATIONS.get(m["variant_key"])
        if variant:
            status = "🟢" if m["equipped"] else "🔵"
            buttons.append([InlineKeyboardButton(text=f"{status} [Ур. {m['level']}] {variant['name']}", callback_data=f"mut_act_det_{m['variant_key']}")])
            
    buttons.append([InlineKeyboardButton(text="🏠 Назад в меню", callback_data="back_to_mut_shop")])
    
    try: await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except: 
        await call.message.delete()
        await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()

@router.callback_query(F.data == "back_to_mut_shop")
async def back_to_mut_shop(call: CallbackQuery, state: FSMContext):
    await state.set_state(Nav.mutations_shop)
    text, ikb = await _shop_menu(call.from_user.id)
    try: await call.message.edit_text(text, reply_markup=ikb)
    except: 
        await call.message.delete()
        await call.message.answer(text, reply_markup=ikb)
    await call.answer()

# ---------------- ДЕТАЛИ И УЛУЧШЕНИЕ ----------------
@router.callback_query(F.data.startswith("mut_pass_det_"))
async def show_passive_detail(call: CallbackQuery):
    # mut_pass_det_{key}_{page}
    parts = call.data.split("_")
    page = parts[-1]
    variant_key = "_".join(parts[3:-1])
    
    user = await database.run_async(database.get_user, call.from_user.id)
    owned = await database.run_async(database.get_user_mutations_v3, call.from_user.id)
    m = next((x for x in owned if x["variant_key"] == variant_key), None)
    
    variant = PASSIVE_MUTATIONS[variant_key]
    upg_cost = cost_upgrade_mutation(m["level"])
    
    text = (
        f"<b>{variant['name']}</b> (Ур. {m['level']})\nТип: Пассивная\n\n"
        f"🛡 <b>Базовый эффект:</b> (Для всех)\n"
    )
    for st, val in variant.get("base_buff", {}).items(): 
        clean_st = st.replace("mult_", "").replace("flat_", "")
        st_name = STAT_LABELS.get(clean_st, clean_st)
        if st.startswith("mult_"):
            text += f"• +{val * m['level'] * 100:.1f}% к {st_name}\n"
        else:
            text += f"• +{val * m['level']:.1f} к {st_name}\n"
    
    text += f"\n💎 <b>Синергия:</b> (Только для кристалла {variant['crystal']})\n"
    for st, val in variant.get("synergy_buff", {}).items(): 
        clean_st = st.replace("mult_", "").replace("flat_", "")
        st_name = STAT_LABELS.get(clean_st, clean_st)
        if st.startswith("mult_"):
            text += f"• +{val * m['level'] * 100:.1f}% к {st_name}\n"
        else:
            text += f"• +{val * m['level']:.1f} к {st_name}\n"
    
    text += f"\n💰 ДНК: {format_number(user['dna_points'])} 🧬"
    
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Улучшить ({format_number(upg_cost)} 🧬)", callback_data=f"upg_pass_{variant_key}_{page}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"open_passives_{page}")]
    ])
    await call.message.edit_text(text, reply_markup=ikb)

# --- Внутренняя функция отрисовки (чтобы больше не было ошибок с ключами) ---
async def _render_active_detail(call: CallbackQuery, variant_key: str):
    user = await database.run_async(database.get_user, call.from_user.id)
    owned = await database.run_async(database.get_user_mutations_v3, call.from_user.id)
    m = next((x for x in owned if x["variant_key"] == variant_key), None)
    
    variant = ACTIVE_MUTATIONS[variant_key]
    upg_cost = cost_upgrade_mutation(m["level"])
    
    text = f"<b>{variant['name']}</b> (Ур. {m['level']})\nСлот: {MUTATION_SLOT_NAMES[variant['slot']]}\n\n"
    text += f"📉 <b>Дебафф (Штраф):</b>\n"
    for st, val in variant.get("debuff", {}).items(): 
        clean_st = st.replace("mult_", "").replace("flat_", "")
        st_name = STAT_LABELS.get(clean_st, clean_st)
        text += f"• -{val * 100:.0f}% к {st_name}\n"
    
    text += f"\n✨ <b>Способность:</b>\n{variant['desc']}\n\n💰 ДНК: {format_number(user['dna_points'])} 🧬"
    
    equip_btn = "⬇️ Снять" if m["equipped"] else "⬆️ Надеть"
    equip_action = f"unequip_act_{variant_key}" if m["equipped"] else f"equip_act_{variant_key}"
    
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=equip_btn, callback_data=equip_action), InlineKeyboardButton(text=f"Улучшить ({format_number(upg_cost)} 🧬)", callback_data=f"upg_act_{variant_key}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="open_actives")]
    ])
    await call.message.edit_text(text, reply_markup=ikb)

# --- Обработчики нажатий ---
@router.callback_query(F.data.startswith("mut_act_det_"))
async def show_active_detail(call: CallbackQuery):
    variant_key = call.data.replace("mut_act_det_", "")
    await _render_active_detail(call, variant_key)

@router.callback_query(F.data.startswith("equip_act_"))
async def equip_act(call: CallbackQuery):
    key = call.data.replace("equip_act_", "")
    await database.run_async(database.equip_active_mutation, call.from_user.id, key)
    await call.answer("Надето!")
    await _render_active_detail(call, key)

@router.callback_query(F.data.startswith("unequip_act_"))
async def unequip_act(call: CallbackQuery):
    key = call.data.replace("unequip_act_", "")
    await database.run_async(database.unequip_active_mutation, call.from_user.id, key)
    await call.answer("Снято!")
    await _render_active_detail(call, key)

@router.callback_query(F.data.startswith("unequip_act_"))
async def unequip_act(call: CallbackQuery):
    key = call.data.replace("unequip_act_", "")
    await database.run_async(database.unequip_active_mutation, call.from_user.id, key)
    await call.answer("Снято!")
    
    # Подменяем данные, чтобы функция отрисовки поняла, какую мутацию показывать
    call.data = f"mut_act_det_{key}"
    await show_active_detail(call)

@router.callback_query(F.data.startswith("upg_pass_"))
async def upg_pass(call: CallbackQuery):
    parts = call.data.split("_")
    page = parts[-1]
    key = "_".join(parts[2:-1])
    await _handle_upgrade(call, key, lambda c: show_passive_detail(c))

@router.callback_query(F.data.startswith("upg_act_"))
async def upg_act(call: CallbackQuery):
    key = call.data.replace("upg_act_", "")
    await _handle_upgrade(call, key, lambda c: show_active_detail(c))

async def _handle_upgrade(call, variant_key, refresh_func):
    owned = await database.run_async(database.get_user_mutations_v3, call.from_user.id)
    m = next((x for x in owned if x["variant_key"] == variant_key), None)
    cost = cost_upgrade_mutation(m["level"])
    spent = await database.run_async(database.try_spend, call.from_user.id, "dna_points", cost)
    if spent:
        await database.run_async(database.upgrade_mutation_v3, call.from_user.id, variant_key)
        await call.answer(f"Уровень повышен до {m['level'] + 1}!")
    else: await call.answer(f"Нужно {format_number(cost)} 🧬", show_alert=True)
    
    # Чтобы обновить данные в call.data, подменим его временно, чтобы refresh_func корректно отработал
    original_data = call.data
    if "upg_pass_" in original_data: call.data = original_data.replace("upg_pass_", "mut_pass_det_")
    elif "upg_act_" in original_data: call.data = original_data.replace("upg_act_", "mut_act_det_")
    await refresh_func(call)

# ---------------- СУНДУКИ И ИВЕНТЫ ----------------
@router.callback_query(F.data.startswith("open_chest_"))
async def open_event_chest(call: CallbackQuery):
    chest_type_raw = call.data.replace("open_chest_", "")
    chest_type = int(chest_type_raw) if chest_type_raw.isdigit() else chest_type_raw
    user_id = call.from_user.id
    
    has_chest = await database.run_async(database.try_spend_chest, user_id, chest_type, 1)
    if not has_chest:
        await call.answer("У тебя нет этого сундука!", show_alert=True)
        return
        
    try: await call.answer("Открываем сундук...")
    except: pass
        
    owned_mutations = await database.run_async(database.get_user_mutations_v3, user_id)
    owned_keys = [m["variant_key"] for m in owned_mutations if m["is_active"] == 1]
    
    loot = await database.run_async(roll_chest_loot, chest_type, owned_keys)
    user = await database.run_async(database.get_user, user_id)
    if loot["shells"] > 0:
        await database.run_async(database.update_user, user_id, nautilus_shells=user["nautilus_shells"] + loot["shells"])
        
    stone_texts = []
    for color, lvl in loot["stones"]:
        await database.run_async(database.add_stone, user_id, color, lvl, 1)
        stone_texts.append(f"{STONE_COLORS[color]['name']} камень (ур. {lvl})")
        
    mut_text = ""
    if loot["mutation"]:
        mut = loot["mutation"]
        # Активные мутации из сундука (is_active=1)
        await database.run_async(database.add_new_mutation_v3, user_id, mut["key"], is_active=1)
        mut_text = f"\n\n🎉 <b>ЛЕГЕНДАРНЫЙ ДРОП!</b>\nТебе выпала Ивентовая мутация: <b>{mut['name']}</b>!\nЗагляни в Инвентарь -> Активные, чтобы надеть её."
        
    shells_text = f"🐚 Ракушки наутилуса: {loot['shells']} шт.\n" if loot["shells"] > 0 else ""
    stones_str = "\n".join([f"💎 {st}" for st in stone_texts]) if stone_texts else "Ничего примечательного."
    
    final_text = f"🎁 <b>Сундук открыт!</b> Вот твоя добыча:\n\n{shells_text}{stones_str}{mut_text}"
    await call.message.edit_text(final_text)
