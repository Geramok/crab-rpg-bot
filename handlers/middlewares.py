# -*- coding: utf-8 -*-
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.fsm.context import FSMContext

import database

class EnsureUserMiddleware(BaseMiddleware):
    """
    Проверяет, есть ли пользователь в базе. Если нет (например, БД сбросилась),
    мягко просит написать /start, не крашась при маршрутизации состояний.
    """
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        state: FSMContext = data.get("state")
        
        if user and state is not None:
            user_db = await database.run_async(database.get_user, user.id)
            if not user_db:
                await state.clear()
                text = (
                    "⚠️ Кажется, твой профиль был сброшен или база обновилась.\n"
                    "Пожалуйста, нажми /start, чтобы начать заново — "
                    "просто извиняемся, разработка всё в одном лице :("
                )
                if event.message:
                    await event.message.answer(text)
                elif event.callback_query:
                    await event.callback_query.answer(text, show_alert=True)
                return
                
        return await handler(event, data)


class SyncBufferMiddleware(BaseMiddleware):
    """Автоматически сохраняет буфер при выходе из боя."""
    async def __call__(self, handler, event: TelegramObject, data: dict):
        state: FSMContext = data.get("state")
        user = data.get("event_from_user")
        
        if user and state:
            current_state = await state.get_state()
            redis_client = state.storage.redis
            
            # Если игрок вышел из состояния охоты в другие меню
            if current_state != "Nav:hunt":
                await database.flush_user_buffer(redis_client, user.id)
            
            # Если игрок в бою, но нажал кнопку другого меню (не связанную с атакой)
            elif event.callback_query and not event.callback_query.data.startswith(("hunt_", "ability_", "pick_guard")):
                await database.flush_user_buffer(redis_client, user.id)
                
        return await handler(event, data)
