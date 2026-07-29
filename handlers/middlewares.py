# -*- coding: utf-8 -*-
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

import database


class EnsureUserMiddleware(BaseMiddleware):
    """Если у пользователя есть FSM-состояние (он вроде бы уже играет), но его
    записи нет в базе данных (например, БД сбросилась при перезапуске контейнера
    на хостинге), — не даём хендлерам упасть с NoneType-ошибкой, а мягко
    возвращаем игрока на /start."""

    async def __call__(self, handler, event: TelegramObject, data):
        state = data.get("state")
        from_user = getattr(event, "from_user", None)
        user_id = from_user.id if from_user else None
        is_callback = hasattr(event, "message") and hasattr(event, "data")

        if user_id is not None and state is not None:
            cur_state = await state.get_state()
            if cur_state is not None:
                user = await database.run_async(database.get_user, user_id)
                if user is None:
                    await state.clear()
                    text = (
                        "⚠️ Похоже, твой прогресс был сброшен (это временная проблема "
                        "хранения данных на сервере). Нажми /start, чтобы начать заново — "
                        "прости за неудобство, разработчик уже в курсе и чинит хранилище."
                    )
                    if is_callback:
                        await event.answer("Прогресс сброшен, нажми /start", show_alert=True)
                        if event.message:
                            await event.message.answer(text)
                    else:
                        await event.answer(text)
                    return None

        return await handler(event, data)
