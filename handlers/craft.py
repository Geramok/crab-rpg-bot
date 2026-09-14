# -*- coding: utf-8 -*-
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import NECTARS_DATA, RESOURCES, STONE_COLORS
from keyboards import kb, BACK
from states import Nav

router = Router()

async def _craft_menu_text_and_kb(user_id, selected_nectar=None):
    nectar_db = await database.get_nectars_data(user_id)
    inv = nectar_db["nectars_inv"]
    active = nectar_db["active_nectar"]
    
    text = "🍯 <b>Лаборатория Нектаров</b>\n\nВыбери рецепт для изучения и крафта:\n"
    buttons = []
    
    row = []
    for key, data in NECTARS_DATA.items():
        emoji = data['name'].split()[0]
        count = inv.get(key, 0)
        mark = "✅ " if active == key else ""
        row.append(InlineKeyboardButton(text=f"{mark}{emoji} ({count})", callback_data=f"select_nectar_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if selected_nectar and selected_nectar in NECTARS_DATA:
        data = NECTARS_DATA[selected_nectar]
        text += f"\n──────────────\n<b>{data['name']}</b>\n<i>{data['desc']}</i>\n\n"
        text += "<b>Стоимость крафта:</b>\n"
        
        for res_key, req_count in data["res_cost"].items():
            text += f"• {RESOURCES[res_key]['name']}: {req_count} шт.\n"
            
        st = data["stone_cost"]
        text += f"• {STONE_COLORS[st['color']]['name']} камень (ур.{st['level']}): {st['count']} шт.\n"
        
        text += f"\nВ инвентаре: {inv.get(selected_nectar, 0)} шт."
        
        # Кнопки действий
        action_row = [InlineKeyboardButton(text="🔨 Скрафтить", callback_data=f"do_craft_{selected_nectar}")]
        if inv.get(selected_nectar, 0) > 0:
            if active == selected_nectar:
                action_row.append(InlineKeyboardButton(text="⬇️ Снять", callback_data=f"equip_nectar_none"))
            else:
                action_row.append(InlineKeyboardButton(text="⬆️ Надеть в бой", callback_data=f"equip_nectar_{selected_nectar}"))
        buttons.append(action_row)

    return text, InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(F.text.in_({"🍯 Нектары", "🍯 Нектар"}))
async def show_craft(message: Message, state: FSMContext):
    await state.set_state(Nav.craft_menu)
    text, ikb = await _craft_menu_text_and_kb(message.from_user.id)
    await message.answer("Спускаемся в лабораторию зелий...", reply_markup=kb([BACK]))
    await message.answer(text, reply_markup=ikb)
    
@router.callback_query(F.data.startswith("select_nectar_"))
async def select_nectar(call: CallbackQuery):
    nectar_key = call.data.replace("select_nectar_", "")
    text, ikb = await _craft_menu_text_and_kb(call.from_user.id, nectar_key)
    try:
        await call.message.edit_text(text, reply_markup=ikb)
    except:
        pass
    await call.answer()

@router.callback_query(F.data.startswith("equip_nectar_"))
async def equip_nectar(call: CallbackQuery):
    nectar_key = call.data.replace("equip_nectar_", "")
    if nectar_key == "none":
        nectar_key = None
    
    await database.update_nectars_data(call.from_user.id, active_nectar=nectar_key)
    await call.answer("Экипировка обновлена!")
    text, ikb = await _craft_menu_text_and_kb(call.from_user.id, nectar_key if nectar_key else None)
    await call.message.edit_text(text, reply_markup=ikb)

@router.callback_query(F.data.startswith("do_craft_"))
async def do_craft(call: CallbackQuery):
    nectar_key = call.data.replace("do_craft_", "")
    user_id = call.from_user.id
    data = NECTARS_DATA[nectar_key]
    
    # Проверка ресурсов
    resources = await database.run_async(database.get_resources, user_id)
    for res_key, req_count in data["res_cost"].items():
        if resources.get(res_key, 0) < req_count:
            await call.answer(f"Не хватает ресурса: {RESOURCES[res_key]['name']}!", show_alert=True)
            return
            
    # Проверка камней
    st = data["stone_cost"]
    stones = await database.run_async(database.get_stones, user_id)
    has_stone = False
    for s in stones:
        if s['color'] == st['color'] and s['level'] == st['level'] and s['count'] >= st['count']:
            has_stone = True
            break
            
    if not has_stone:
        await call.answer("Не хватает нужных камней!", show_alert=True)
        return

    # Списание через run_async
    for res_key, req_count in data["res_cost"].items():
        success_res = await database.run_async(database.try_spend_resource, user_id, res_key, req_count)
        if not success_res:
            await call.answer("Ошибка списания ресурсов!", show_alert=True)
            return
            
    success_stone = await database.run_async(database.try_spend_stone, user_id, st['color'], st['level'], st['count'])
    if not success_stone:
        await call.answer("Ошибка списания камней!", show_alert=True)
        return
    
    # Выдача нектара
    nectar_db = await database.get_nectars_data(user_id)
    inv = nectar_db["nectars_inv"]
    inv[nectar_key] = inv.get(nectar_key, 0) + 1
    await database.update_nectars_data(user_id, nectars_inv=inv)
    
    await call.answer(f"Скрафчено: {data['name']}!", show_alert=True)
    text, ikb = await _craft_menu_text_and_kb(user_id, nectar_key)
    
    try:
        await call.message.edit_text(text, reply_markup=ikb)
    except TelegramBadRequest:
        pass
