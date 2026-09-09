# -*- coding: utf-8 -*-
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database
from events_logic import finish_event

router = Router()

# Укажи свой числовой Telegram ID без кавычек
ADMIN_ID = ТВОЙ_TELEGRAM_ID

@router.message(Command("endboss"))
async def admin_end_boss(message: Message):
    # Защита: если команду пишет обычный игрок, бот просто промолчит
    if message.from_user.id != ADMIN_ID:
        return 

    # Проверяем, есть ли сейчас активный босс
    event = await database.run_async(database.get_active_event)
    if not event:
        await message.answer("Сейчас нет активных мифических ивентов.")
        return

    await message.answer(f"🔧 Админ-команда: досрочно завершаю ивент «{event['name']}»...")
    
    # Вызываем нашу логику, которая закрывает ивент и раздаёт сундуки
    await finish_event(message.bot, event)
