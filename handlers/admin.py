# -*- coding: utf-8 -*-
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database
from config import ADMIN_IDS
from events_logic import finish_event

router = Router()


def _is_admin(user_id):
    return user_id in ADMIN_IDS


@router.message(Command("startboss"))
async def start_boss(message: Message):
    if not _is_admin(message.from_user.id):
        return
    # формат: /startboss 72 Повелитель морей | Кракен пробудился в глубинах...
    # (мифические ивенты запускаются автоматически планировщиком — эта команда
    # нужна только для ручного/особого ивента вне расписания)
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or "|" not in args[1]:
        await message.answer(
            "Формат: /startboss <часов> <имя босса> | <описание>\n"
            "Пример: /startboss 72 Кракен | Повелитель морей пробудился!"
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
    if await database.run_async(database.get_active_event):
        await message.answer("Уже есть активный ивент. Сначала заверши его через /endboss.")
        return
    event_id = await database.run_async(
        database.create_event, name.strip(), description.strip(), int(hours * 3600)
    )
    await message.answer(f"Ивент «{name.strip()}» запущен на {hours} ч. (id={event_id})")


@router.message(Command("endboss"))
async def end_boss(message: Message):
    if not _is_admin(message.from_user.id):
        return
    event = await database.run_async(database.get_active_event)
    if not event:
        await message.answer("Нет активного ивента.")
        return

    results = await finish_event(message.bot, event)
    if not results:
        await message.answer(
            "Ивент завершён. Активных участников (с достаточным уроном) не нашлось, "
            "особые награды не выданы, но базовые (раковины/камни) получили все, кто атаковал."
        )
        return

    lines = [f"Ивент «{event['name']}» завершён. Жемчужные кейсы выпали:"]
    for uid, special in results:
        user = await database.run_async(database.get_user, uid)
        name = user["nickname"] if user else uid
        lines.append(f"— {name}: получена мутация")
    await message.answer("\n".join(lines))
