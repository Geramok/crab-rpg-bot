# -*- coding: utf-8 -*-
from aiogram import Router
from aiogram.types import Message

import database
from data import STONE_COLORS, MUTATION_SLOTS, SPECIAL_MUTATIONS
from keyboards import kb, BACK

router = Router()


async def show_inventory(message: Message):
    user = database.get_user(message.from_user.id)
    stones = database.get_stones(message.from_user.id)
    mutations = database.get_mutations(message.from_user.id)
    special = database.get_special_mutations(message.from_user.id)

    text = (
        f"🎒 <b>Инвентарь</b>\n\n"
        f"💰 Золото: {user['gold']}\n"
        f"🧬 Очки ДНК: {user['dna_points']}\n"
        f"🐚 Раковины наутилуса: {user['nautilus_shells']}\n\n"
        f"<b>Камни:</b>\n"
    )
    if stones:
        for s in sorted(stones, key=lambda x: (x["color"], x["level"])):
            text += f"{STONE_COLORS[s['color']]['name']} (ур. {s['level']}) × {s['count']}\n"
    else:
        text += "пока пусто\n"

    text += "\n<b>Мутации:</b>\n"
    any_mut = False
    for slot, m in mutations.items():
        if m["level"] > 0:
            any_mut = True
            status = "✅ надета" if m["equipped"] else "выключена"
            text += f"{MUTATION_SLOTS[slot]['name']} — ур. {m['level']} ({status})\n"
    for key, v in special.items():
        any_mut = True
        status = "✅ надета" if v["equipped"] else "выключена"
        text += f"{SPECIAL_MUTATIONS[key]['name']} ({status})\n"
    if not any_mut:
        text += "пока нет мутаций\n"

    await message.answer(text, reply_markup=kb([BACK]))
