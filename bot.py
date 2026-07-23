# -*- coding: utf-8 -*-
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db

from handlers import start, menu, hunt, mutations, profile, dig, inventory, misc, admin, shop
from handlers.middlewares import EnsureUserMiddleware
from events_scheduler import events_scheduler_loop

logging.basicConfig(level=logging.INFO)


async def main():
    init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Защита: если FSM-состояние есть, а пользователя в БД нет (например, БД
    # сбросилась при перезапуске контейнера) — мягкий возврат на /start вместо падения
    dp.message.middleware(EnsureUserMiddleware())
    dp.callback_query.middleware(EnsureUserMiddleware())

    # Порядок важен: admin и start — раньше общих меню-хендлеров
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(hunt.router)
    dp.include_router(mutations.router)
    dp.include_router(profile.router)
    dp.include_router(shop.router)
    dp.include_router(dig.router)
    dp.include_router(inventory.router)
    dp.include_router(misc.router)

    await bot.delete_webhook(drop_pending_updates=True)

    # Фоновый планировщик мифических ивентов — сам стартует/завершает боссов,
    # админу ничего нажимать не нужно (но /startboss и /endboss всё ещё доступны)
    asyncio.create_task(events_scheduler_loop(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
