# -*- coding: utf-8 -*-
import random

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

import database
from config import ADMIN_IDS
from data import STONE_COLORS, SPECIAL_MUTATIONS

router = Router()


def _is_admin(user_id):
    return user_id in ADMIN_IDS


@router.message(Command("startboss"))
async def start_boss(message: Message):
    if not _is_admin(message.from_user.id):
        return
    # формат: /startboss 72 Повелитель морей | Кракен пробудился в глубинах...
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or "|" not in args[1]:
        await message.answer(
            "Формат: /startboss <часов> <имя босса> | <описание>\n"
            "Пример: /startboss 72 Кракен | Повелитель морей пробудился! Наносите урон, чтобы получить награды."
        )
        return

    rest = args[1]
    hours_str, tail = rest.split(maxsplit=1)
    try:
        hours = float(hours_str)
    except ValueError:
        await message.answer("Первым аргументом укажи число часов.")
        return

    name, description = tail.split("|", 1)
    event_id = database.create_event(name.strip(), description.strip(), int(hours * 3600))
    await message.answer(f"Ивент «{name.strip()}» запущен на {hours} ч. (id={event_id})")


@router.message(Command("endboss"))
async def end_boss(message: Message):
    if not _is_admin(message.from_user.id):
        return
    event = database.get_active_event()
    if not event:
        await message.answer("Нет активного ивента.")
        return

    lb = database.get_event_leaderboard(event["id"], 100)
    database.close_event(event["id"])

    if not lb:
        await message.answer("Ивент завершён, но никто не участвовал.")
        return

    results = []
    for i, row in enumerate(lb, 1):
        uid = row["user_id"]
        user = database.get_user(uid)
        if not user:
            continue
        database.update_user(uid, boss_kills=user["boss_kills"] + 1)

        shells = 0
        stone_gifts = []
        special = None

        if i == 1:
            shells = 15
            stone_gifts = [(random.choice(list(STONE_COLORS.keys())), 3) for _ in range(3)]
            special = random.choice(list(SPECIAL_MUTATIONS.keys()))
        elif i <= 5:
            shells = 7
            stone_gifts = [(random.choice(list(STONE_COLORS.keys())), 2) for _ in range(2)]
            if random.random() < 0.3:
                special = random.choice(list(SPECIAL_MUTATIONS.keys()))
        elif i <= 20:
            shells = 2
            stone_gifts = [(random.choice(list(STONE_COLORS.keys())), 1)]

        if shells:
            database.update_user(uid, nautilus_shells=user["nautilus_shells"] + shells)
        for color, level in stone_gifts:
            database.add_stone(uid, color, level, 1)
        if special:
            database.add_special_mutation(uid, special)

        try:
            await message.bot.send_message(
                uid,
                f"🐉 Ивент «{event['name']}» завершён! Ты занял {i} место по урону.\n"
                f"Награды: 🐚 {shells} раковин"
                + (f", камни" if stone_gifts else "")
                + (f", особая мутация «{SPECIAL_MUTATIONS[special]['name']}»!" if special else "."),
            )
        except Exception:
            pass
        results.append(f"{i}. {user['nickname']} — {row['damage']} урона")

    await message.answer("Ивент завершён, награды разосланы.\n\n" + "\n".join(results[:20]))
