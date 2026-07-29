# -*- coding: utf-8 -*-
import time

from aiogram import Router
from aiogram.types import Message

import database
from data import STONE_COLORS, SPECIAL_MUTATIONS, RESOURCES
from game_logic import get_mutation_variant
from keyboards import kb, BACK

router = Router()


async def show_inventory(message: Message):
    user = await database.run_async(database.get_user, message.from_user.id)
    stones = await database.run_async(database.get_stones, message.from_user.id)
    mutations = await database.run_async(database.get_mutations, message.from_user.id)
    special = await database.run_async(database.get_special_mutations, message.from_user.id)
    resources = await database.run_async(database.get_resources, message.from_user.id)

    text = f"🐚 <b>Нора</b>\n\n💰{user['gold']} 🧬{user['dna_points']} 🐚{user['nautilus_shells']}\n\n"

    if stones:
        stones_txt = ", ".join(
            f"{STONE_COLORS[s['color']]['name']}·{s['level']}×{s['count']}"
            for s in sorted(stones, key=lambda x: (x["color"], x["level"]))
        )
    else:
        stones_txt = "пусто (копай камни автоматически применяются)"
    text += f"Камни: {stones_txt}\n"

    res_txt = ", ".join(f"{info['name']}×{resources.get(key, 0)}" for key, info in RESOURCES.items())
    text += f"Ресурсы: {res_txt}\n"

    mutation_names = []
    for slot, m in mutations.items():
        if m["level"] > 0 and m.get("variant_key"):
            variant = get_mutation_variant(slot, m["variant_key"])
            if variant:
                status = "✅" if m["equipped"] else "⭕"
                mutation_names.append(f"{variant['name']}·{m['level']}{status}")
    for key, v in special.items():
        status = "✅" if v["equipped"] else "⭕"
        mutation_names.append(f"{SPECIAL_MUTATIONS[key]['name']}{status}")
    text += f"Мутации: {', '.join(mutation_names) if mutation_names else 'нет'}"

    now = int(time.time())
    if user["buff_expires_ts"] and user["buff_expires_ts"] > now:
        left_min = (user["buff_expires_ts"] - now) // 60 + 1
        text += f"\n✨ Нектар силы активен ещё {left_min} мин."
    if user["permanent_boost"]:
        text += "\n🌟 Вечный прилив: +15% к золоту/ДНК навсегда"

    await message.answer(text, reply_markup=kb([BACK]))
