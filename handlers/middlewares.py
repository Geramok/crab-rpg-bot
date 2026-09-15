# -*- coding: utf-8 -*-
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database

class EnsureUserMiddleware(BaseMiddleware):
    """
    Проверяет, есть ли пользователь в базе. Если нет (например, БД сбросилась),
    мягко просит написать /start, не крашась при маршрутизации состояний.
    """
    async def __call__(self, handler, event: TelegramObject, data: dict):
        # 1. Извлекаем пользователя и его текущее состояние (FSM) из данных события
        user = data.get("event_from_user")
        state: FSMContext = data.get("state")
        
        # 2. ИСКЛЮЧЕНИЕ ДЛЯ РЕГИСТРАЦИИ:
        # Проверяем, является ли событие текстовым сообщением и начинается ли оно с /start
        # Если да, мы сразу пропускаем его дальше, чтобы код в start.py мог создать профиль.
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)
            
        # 3. ПРОВЕРКА ОСТАЛЬНЫХ ДЕЙСТВИЙ:
        if user and state is not None:
            # Делаем запрос к базе данных, чтобы найти профиль игрока
            user_db = await database.run_async(database.get_user, user.id)
            
            # Если профиль не найден (база удалилась или игрок как-то обошел регистрацию)
            if not user_db:
                # Очищаем состояние игрока, чтобы он не застрял в старом меню
                await state.clear()
                
                # Текст ошибки
                text = (
                    "⚠️ Кажется, твой профиль был сброшен или база обновилась.\n"
                    "Пожалуйста, нажми /start, чтобы начать заново — "
                    "просто извиняемся, разработка всё в одном лице :("
                )
                
                # Отправляем сообщение-предупреждение
                # Если игрок просто написал текст:
                if isinstance(event, Message):
                    await event.answer(text)
                # Если игрок нажал на инлайн-кнопку:
                elif isinstance(event, CallbackQuery):
                    await event.answer(text, show_alert=True)
                    
                # Прерываем выполнение (return без вызова handler), 
                # чтобы бот не пытался обработать действие несуществующего игрока
                return
                
        # 4. ПРОДОЛЖЕНИЕ РАБОТЫ:
        # Если игрок есть в базе, передаем событие дальше твоим обработчикам
        return await handler(event, data)


class SyncBufferMiddleware(BaseMiddleware):
    """Автоматически сохраняет буфер при выходе из боя."""
    async def __call__(self, handler, event: TelegramObject, data: dict):
        # 1. Извлекаем состояние и пользователя
        state: FSMContext = data.get("state")
        user = data.get("event_from_user")
        
        if user and state:
            current_state = await state.get_state()
            redis_client = state.storage.redis
            
            # 2. ПРОВЕРКА ВЫХОДА ИЗ БОЯ:
            # Сценарий А: Игрок вышел из состояния охоты (Nav:hunt) в любое другое меню
            if current_state != "Nav:hunt":
                # Сбрасываем данные из кэша (Redis) в основную базу (SQLite)
                await database.flush_user_buffer(redis_client, user.id)
            
            # Сценарий Б: Игрок формально в бою, но нажал инлайн-кнопку ДРУГОГО меню
            # (кнопка не начинается на hunt_, ability_ или pick_guard)
            elif isinstance(event, CallbackQuery) and not event.data.startswith(("hunt_", "ability_", "pick_guard")):
                # Также сохраняем данные, чтобы они не потерялись при переходе
                await database.flush_user_buffer(redis_client, user.id)
                
        # 3. Передаем обработку дальше
        return await handler(event, data)
