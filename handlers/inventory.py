# -*- coding: utf-8 -*-
from aiogram import Router
from aiogram.types import Message

import database
from data import STONE_COLORS, MUTATION_SLOT_NAMES, SPECIAL_MUTATIONS, STAT_LABELS
from game_logic import get_mutation_variant
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
        f"<b>Камни</b> (применяются автоматически, ничего нажимать не нужно):\n"
    )
    if stones:
        for s in sorted(stones, key=lambda x: (x["color"], x["level"])):
            text += f"{STONE_COLORS[s['color']]['name']} (ур. {s['level']}) × {s['count']}\n"
    else:
        text += "пока пусто\n"

    text += "\n<b>Мутации-артефакты:</b>\n"
    any_mut = False
    for slot, m in mutations.items():
        if m["level"] > 0 and m.get("variant_key"):
            variant = get_mutation_variant(slot, m["variant_key"])
            if not variant:
                continue
            any_mut = True
            status = "✅ надета" if m["equipped"] else "выключена"
            buff = variant["buff_per_level"] * m["level"]
            debuff = variant["debuff_per_level"] * m["level"]
            text += (
                f"{MUTATION_SLOT_NAMES[slot]}: {variant['name']} — ур. {m['level']} ({status})\n"
                f"  +{buff:.1f} {STAT_LABELS[variant['buff_stat']]}, -{debuff:.1f} {STAT_LABELS[variant['debuff_stat']]}\n"
            )
    for key, v in special.items():
        any_mut = True
        status = "✅ надета" if v["equipped"] else "выключена"
        text += f"{SPECIAL_MUTATIONS[key]['name']} ({status})\n"
    if not any_mut:
        text += "пока нет мутаций\n"

    await message.answer(text, reply_markup=kb([BACK]))
