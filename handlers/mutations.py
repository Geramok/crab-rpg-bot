# -*- coding: utf-8 -*-
import random

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import MUTATION_SLOT_NAMES, STAT_LABELS, MUTATION_VARIANTS, SPECIAL_MUTATIONS
from game_logic import (
    molt_required_level, dna_points_for_molt, cost_new_mutation, cost_upgrade_mutation,
    roll_mutation_variant, get_mutation_variant, apply_permanent_boost, format_number
)
from keyboards import mutations_root_kb, kb, BACK
from states import Nav

router = Router()

def _molt_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, сбросить уровень", callback_data="molt_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="molt_cancel"),
    ]])

@router.message(Nav.mutations_root, F.text == "🧬 Линька")
async def molt_request(message: Message, state: FSMContext):
    user = await database.run_async(database.get_user, message.from_user.id)
    required = molt_required_level(user["molts"])
    if user["crab_level"] < required:
        await message.answer(
            f"Линька доступна с {required} уровня краба (это твоя {user['molts'] + 1}-я линька — "
            f"с каждой следующей линькой требуемый уровень растёт).\n"
            f"Твой текущий уровень: {user['crab_level']}.",
            reply_markup=mutations_root_kb(),
        )
        return

    gain = apply_permanent_boost(dna_points_for_molt(user["molts"], user["crab_level"]), user)
    over = user["crab_level"] - required
    bonus_txt = f" (в т.ч. +{round(over * 0.4)} за {over} уровней сверх минимума)" if over > 0 else ""
    await message.answer(
        f"⚠️ Линька сбросит твой уровень краба ({user['crab_level']} → 1) и всё золото ({format_number(user['gold'])} 💰).\n"
        f"Взамен ты получишь <b>{format_number(gain)}</b> очков ДНК 🧬{bonus_txt} "
        f"(мутации и уже накопленные очки сохранятся).\n\n"
        f"Провести линьку?",
        reply_markup=_molt_confirm_kb(),
    )

@router.callback_query(F.data == "molt_confirm")
async def molt_confirm(call: CallbackQuery, state: FSMContext):
    user = await database.run_async(database.get_user, call.from_user.id)
    required = molt_required_level(user["molts"])
    if user["crab_level"] < required:
        await call.answer("Условие для линьки больше не выполняется.", show_alert=True)
        return

    gain = apply_permanent_boost(dna_points_for_molt(user["molts"], user["crab_level"]), user)
    
    await database.run_async(
        database.update_user,
        call.from_user.id,
        crab_level=1,
        gold=0,
        dna_points=user["dna_points"] + gain,
        molts=user["molts"] + 1,
        total_dna_earned=user["total_dna_earned"] + gain,
        cur_meters=1,
    )
    next_required = molt_required_level(user["molts"] + 1)
    await call.message.edit_text(
        f"🧬 Линька прошла успешно! Получено {format_number(gain)} очков ДНК.\n"
        f"Всего линек: {user['molts'] + 1}. Следующая линька потребует {next_required} уровня."
    )
    await call.answer()

    from handlers.start import prompt_crab_choice
    await prompt_crab_choice(call.message, state)

@router.callback_query(F.data == "molt_cancel")
async def molt_cancel(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Линька отменена.")
    await call.answer()
    await call.message.answer("Что дальше?", reply_markup=mutations_root_kb())


# ---------------- НОВЫЙ МАГАЗИН И ИНВЕНТАРЬ ----------------

async def _shop_menu(user_id):
    user = await database.run_async(database.get_user, user_id)
    owned = await database.run_async(database.get_mutations_v2, user_id)
    new_cost = cost_new_mutation(len(owned))
    
    text = (
        f"🧪 <b>Лаборатория Мутаций</b>\n\n"
        f"Очки ДНК: <b>{format_number(user['dna_points'])} 🧬</b>\n\n"
        f"# ЗДЕСЬ НАПИШИ СВОЮ ИНФОРМАЦИЮ О МУТАЦИЯХ #\n"
        f"<i>Мутации навсегда меняют геном твоего краба. Выбивай новые варианты "
        f"в лаборатории и комбинируй их в инвентаре под свой стиль игры!</i>"
    )
    
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🧬 Купить новую ({format_number(new_cost)})", callback_data="buy_new_mut"),
            InlineKeyboardButton(text="🎒 Инвентарь", callback_data="open_mut_inv")
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
    owned = await database.run_async(database.get_mutations_v2, call.from_user.id)
    owned_keys = [m["variant_key"] for m in owned]

    all_possible = []
    for slot, variants in MUTATION_VARIANTS.items():
        for v in variants:
            if v["key"] not in owned_keys:
                all_possible.append({"key": v["key"], "slot": slot, "name": v["name"]})

    if not all_possible:
        await call.answer("У тебя уже есть все возможные мутации из лаборатории!", show_alert=True)
        return

    cost = cost_new_mutation(len(owned))
    if user["dna_points"] < cost:
        await call.answer(f"Не хватает ДНК! Нужно {format_number(cost)} 🧬", show_alert=True)
        return

    spent = await database.run_async(database.try_spend, call.from_user.id, "dna_points", cost)
    if spent:
        new_mut = random.choice(all_possible)
        await database.run_async(database.add_new_mutation, call.from_user.id, new_mut["key"], new_mut["slot"])
        await call.answer(f"🎉 ГЕНЕТИЧЕСКИЙ ПРОРЫВ!\nВыбита новая мутация:\n{new_mut['name']}!", show_alert=True)
        
        text, ikb = await _shop_menu(call.from_user.id)
        await call.message.edit_text(text, reply_markup=ikb)

@router.callback_query(F.data == "open_mut_inv")
async def open_mut_inv(call: CallbackQuery, state: FSMContext):
    await state.set_state(Nav.mutations_inventory)
    owned = await database.run_async(database.get_mutations_v2, call.from_user.id)
    
    text = (
        "🎒 <b>Инвентарь мутаций</b>\n\n"
        "🟢 — надето сейчас\n"
        "🔵 — лежит в инвентаре\n\n"
        "<i>Выбери мутацию, чтобы посмотреть информацию, улучшить или экипировать:</i>"
    )
    
    buttons = []
    row = []
    for m in owned:
        variant = get_mutation_variant(m["slot"], m["variant_key"])
        if variant:
            emoji = variant["name"].split()[0]
            status = "🟢" if m["equipped"] else "🔵"
            row.append(InlineKeyboardButton(text=f"{status} {emoji}", callback_data=f"mut_det_reg_{m['variant_key']}"))
            
            if len(row) == 4:
                buttons.append(row)
                row = []
                
    if row:
        buttons.append(row)
        
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в лабораторию", callback_data="back_to_mut_shop")])
    
    try:
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except:
        await call.message.delete()
        await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()

@router.callback_query(F.data == "back_to_mut_shop")
async def back_to_mut_shop(call: CallbackQuery, state: FSMContext):
    await state.set_state(Nav.mutations_shop)
    text, ikb = await _shop_menu(call.from_user.id)
    
    try:
        await call.message.edit_text(text, reply_markup=ikb)
    except:
        await call.message.delete()
        await call.message.answer(text, reply_markup=ikb)
    await call.answer()

# ---------------- КАРТОЧКА МУТАЦИИ ----------------

async def _show_mutation_detail(call: CallbackQuery, variant_key: str):
    user = await database.run_async(database.get_user, call.from_user.id)
    m = await database.run_async(database.get_mutation_by_key, call.from_user.id, variant_key)
    variant = get_mutation_variant(m["slot"], variant_key)
    
    buff = variant["buff_per_level"] * m["level"]
    debuff = variant["debuff_per_level"] * m["level"]
    upg_cost = cost_upgrade_mutation(m["level"])
    
    text = (
        f"<b>{variant['name']}</b> (Ур. {m['level']})\n"
        f"Слот: {MUTATION_SLOT_NAMES[m['slot']]}\n\n"
        f"📈 <b>Эффекты:</b>\n"
        f"• +{buff:.1f} к {STAT_LABELS[variant['buff_stat']]}\n"
        f"• -{debuff:.1f} к {STAT_LABELS[variant['debuff_stat']]}\n\n"
    )
    
    if variant.get("desc"):
        text += f"✨ <b>Пассивная способность:</b>\n{variant['desc']}\n\n"
        
    text += f"💰 Твой баланс: {format_number(user['dna_points'])} 🧬"
    
    equip_btn_text = "⬇️ Снять мутацию" if m["equipped"] else "⬆️ Надеть мутацию"
    equip_action = f"unequip_reg_{variant_key}" if m["equipped"] else f"equip_reg_{variant_key}"
    
    buttons = [
        [
            InlineKeyboardButton(text=equip_btn_text, callback_data=equip_action),
            InlineKeyboardButton(text=f"Улучшить ({format_number(upg_cost)} 🧬)", callback_data=f"upgrade_{variant_key}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад в инвентарь", callback_data="open_mut_inv")]
    ]
    ikb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await call.message.delete()
    except:
        pass

    if variant.get("image_id"):
        await call.message.answer_photo(photo=variant["image_id"], caption=text, reply_markup=ikb)
    else:
        await call.message.answer(text, reply_markup=ikb)

@router.callback_query(F.data.startswith("mut_det_reg_"))
async def mut_det_reg(call: CallbackQuery, state: FSMContext):
    await state.set_state(Nav.mutation_detail)
    variant_key = call.data.replace("mut_det_reg_", "")
    await _show_mutation_detail(call, variant_key)
    await call.answer()

@router.callback_query(F.data.startswith("equip_reg_"))
async def action_equip_reg(call: CallbackQuery):
    variant_key = call.data.replace("equip_reg_", "")
    m = await database.run_async(database.get_mutation_by_key, call.from_user.id, variant_key)
    
    await database.run_async(database.equip_mutation, call.from_user.id, variant_key, m["slot"])
    await call.answer("Мутация экипирована!", show_alert=False)
    await _show_mutation_detail(call, variant_key)

@router.callback_query(F.data.startswith("unequip_reg_"))
async def action_unequip_reg(call: CallbackQuery):
    variant_key = call.data.replace("unequip_reg_", "")
    await database.run_async(database.unequip_mutation, call.from_user.id, variant_key)
    await call.answer("Мутация снята!", show_alert=False)
    await _show_mutation_detail(call, variant_key)

@router.callback_query(F.data.startswith("upgrade_"))
async def action_upgrade(call: CallbackQuery):
    variant_key = call.data.replace("upgrade_", "")
    m = await database.run_async(database.get_mutation_by_key, call.from_user.id, variant_key)
    cost = cost_upgrade_mutation(m["level"])
    
    spent = await database.run_async(database.try_spend, call.from_user.id, "dna_points", cost)
    if spent:
        await database.run_async(database.upgrade_mutation, call.from_user.id, variant_key)
        await call.answer(f"Уровень повышен до {m['level'] + 1}!", show_alert=False)
    else:
        await call.answer(f"Не хватает ДНК! Нужно {format_number(cost)} 🧬", show_alert=True)
        
    await _show_mutation_detail(call, variant_key)
