# -*- coding: utf-8 -*-
import time

from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

import database
from data import STONE_COLORS, RESOURCES, EVENT_CHESTS
from game_logic import get_mutation_variant
from keyboards import kb, BACK

router = Router()

async def show_inventory(message: Message):
    user = await database.run_async(database.get_user, message.from_user.id)
    stones = await database.run_async(database.get_stones, message.from_user.id)
    mutations = await database.run_async(database.get_mutations_v2, message.from_user.id)
    resources = await database.run_async(database.get_resources, message.from_user.id)
    chests = await database.run_async(database.get_chests, message.from_user.id)

    separator = "\n──────────────\n"
    text = f"🐚 <b>Нора</b>\n\n💰 <b>{user['gold']}</b>  |  🧬 <b>{user['dna_points']}</b>  |  🐚 <b>{user['nautilus_shells']}</b>\n"

    # 1. Группировка камней
    text += separator
    text += "💎 <b>Камни:</b>\n"
    if stones:
        stones_by_color = {}
        for s in stones:
            stones_by_color.setdefault(s['color'], []).append(s)
        
        for color, st_list in stones_by_color.items():
            color_name = STONE_COLORS[color]['name']
            st_list.sort(key=lambda x: x['level'])
            st_str = " | ".join(f"ур.{s['level']} (×{s['count']})" for s in st_list)
            text += f"{color_name}: {st_str}\n"
    else:
        text += "<i>пусто (добываются при копании)</i>\n"

    # 2. Вывод ресурсов
    text += separator
    text += "📦 <b>Ресурсы:</b>\n"
    res_txt = " | ".join(f"{info['name']} ×{resources.get(key, 0)}" for key, info in RESOURCES.items())
    text += f"{res_txt}\n"

    # 3. Вывод мутаций (Экипированные и В запасе)
    text += separator
    text += "🧪 <b>Мутации:</b>\n"
    equipped = []
    unequipped = []
    
    for m in mutations:
        if m["level"] > 0 and m.get("variant_key"):
            variant = get_mutation_variant(m["slot"], m["variant_key"])
            if variant:
                prefix = "🌟 " if variant.get("is_special") else ""
                mut_name = f"{prefix}{variant['name']} (Ур.{m['level']})"
                if m["equipped"]:
                    equipped.append(f"🟢 {mut_name}")
                else:
                    unequipped.append(f"🔵 {mut_name}")
                    
    if equipped or unequipped:
        if equipped:
            text += "<b>Надето:</b>\n" + "\n".join(equipped) + "\n"
        if unequipped:
            text += "<b>В запасе:</b>\n" + "\n".join(unequipped) + "\n"
    else:
        text += "<i>нет мутаций</i>\n"

    # 4. Вывод активных бустов
    text += separator
    now = int(time.time())
    has_boosts = False
    if user["buff_expires_ts"] and user["buff_expires_ts"] > now:
        left_min = (user["buff_expires_ts"] - now) // 60 + 1
        text += f"✨ Нектар силы: ещё {left_min} мин.\n"
        has_boosts = True
    if user["permanent_boost"]:
        text += "🌟 Вечный прилив: +15% к золоту/ДНК навсегда\n"
        has_boosts = True
        
    if not has_boosts:
        text += "<i>Нет активных усилений</i>\n"

    # 5. Инлайн-кнопки для сундуков
    buttons = []
    if chests:
        for chest_type, count in chests.items():
            if count > 0:
                chest_key = int(chest_type) if str(chest_type).isdigit() else chest_type
                if chest_key in EVENT_CHESTS:
                    chest_name = EVENT_CHESTS[chest_key]['name']
                    buttons.append([InlineKeyboardButton(
                        text=f"🎁 Открыть {chest_name} (×{count})",
                        callback_data=f"open_chest_{chest_key}"
                    )])
                    
    ikb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    # Очищаем нижнюю клавиатуру от лишнего мусора и выводим Нору с инлайн-кнопками
    await message.answer("🎒 Раскладываем запасы...", reply_markup=kb([BACK]))
    await message.answer(text, reply_markup=ikb)
