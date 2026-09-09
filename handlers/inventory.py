# -*- coding: utf-8 -*-
import time

from aiogram import Router
from aiogram.types import Message

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

    text = f"🐚 <b>Нора</b>\n\n💰{user['gold']} 🧬{user['dna_points']} 🐚{user['nautilus_shells']}\n\n"

    # 1. Вывод камней
    if stones:
        stones_txt = ", ".join(
            f"{STONE_COLORS[s['color']]['name']}·{s['level']}×{s['count']}"
            for s in sorted(stones, key=lambda x: (x["color"], x["level"]))
        )
    else:
        stones_txt = "пусто (копай камни автоматически применяются)"
    text += f"Камни: {stones_txt}\n"

    # 2. Вывод ресурсов
    res_txt = ", ".join(f"{info['name']}×{resources.get(key, 0)}" for key, info in RESOURCES.items())
    text += f"Ресурсы: {res_txt}\n"

    # 3. Вывод сундуков с ивентов
    if chests:
        chests_txt_list = []
        for chest_type, count in chests.items():
            # Защита от строковых ключей в БД (превращаем '1' в 1, но оставляем 'default' строкой)
            chest_key = int(chest_type) if str(chest_type).isdigit() else chest_type
            if chest_key in EVENT_CHESTS:
                chests_txt_list.append(f"{EVENT_CHESTS[chest_key]['name']}×{count}")
        chests_txt = ", ".join(chests_txt_list) if chests_txt_list else "нет"
    else:
        chests_txt = "нет"
    text += f"Сундуки: {chests_txt}\n"

    # 4. Вывод обычных и легендарных мутаций (v2)
    mutation_names = []
    for m in mutations:
        if m["level"] > 0 and m.get("variant_key"):
            variant = get_mutation_variant(m["slot"], m["variant_key"])
            if variant:
                status = "✅" if m["equipped"] else "⭕"
                prefix = "🌟 " if variant.get("is_special") else ""
                mutation_names.append(f"{prefix}{variant['name']}·{m['level']}{status}")
                
    text += f"Мутации: {', '.join(mutation_names) if mutation_names else 'нет'}"

    # 5. Вывод активных бустов
    now = int(time.time())
    if user["buff_expires_ts"] and user["buff_expires_ts"] > now:
        left_min = (user["buff_expires_ts"] - now) // 60 + 1
        text += f"\n✨ Нектар силы активен ещё {left_min} мин."
    if user["permanent_boost"]:
        text += "\n🌟 Вечный прилив: +15% к золоту/ДНК навсегда"

    await message.answer(text, reply_markup=kb([BACK]))
