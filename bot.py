# -*- coding: utf-8 -*-
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db

from handlers import start, menu, hunt, mutations, profile, dig, inventory, misc, admin, shop, craft
from handlers.middlewares import EnsureUserMiddleware
from events_scheduler import events_scheduler_loop

logging.basicConfig(level=logging.INFO)

# На некоторых российских хостингах (в т.ч. иногда на Amvera) исходящий
# доступ к api.telegram.org может блокироваться на уровне провайдера/сети
# (это массовая проблема для РФ-хостов, не специфичная для этого бота — см.
# README). Если видишь в логах постоянные 'Request timeout error' на 60+
# секунд — это оно. Лечится прокси: задай переменную окружения PROXY_URL
# (например "http://user:pass@host:port") в настройках проекта, ничего
# менять в коде не нужно.
PROXY_URL = os.getenv("PROXY_URL")


async def _safe_delete_webhook(bot):
    """delete_webhook на старте — это ОДИН сетевой запрос к Telegram, и раньше
    если именно он попадал под сетевую блокировку (см. PROXY_URL выше), падал
    ВЕСЬ процесс бота, а не отдельное действие — приходилось ждать внешнего
    перезапуска. Теперь при сбое просто пробуем ещё раз с паузой, вместо того
    чтобы ронять весь бот из-за одного неудачного запроса."""
    for attempt in range(1, 6):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            return
        except Exception as e:
            logging.warning(f"delete_webhook не удался (попытка {attempt}/5): {e!r}")
            if attempt < 5:
                await asyncio.sleep(5)
    logging.warning("delete_webhook так и не удался за 5 попыток — запускаем polling всё равно.")


async def main():
    init_db()

    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)
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
    dp.include_router(craft.router)
    dp.include_router(misc.router)

    await _safe_delete_webhook(bot)

    # Фоновый планировщик мифических ивентов — сам стартует/завершает боссов,
    # админу ничего нажимать не нужно (но /startboss и /endboss всё ещё доступны)
    asyncio.create_task(events_scheduler_loop(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
