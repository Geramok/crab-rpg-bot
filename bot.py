# -*- coding: utf-8 -*-
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiohttp import web
from redis.asyncio import Redis

from config import BOT_TOKEN, REDIS_DATA_TTL, REDIS_STATE_TTL, REDIS_URL
from database import init_db

from handlers import start, menu, hunt, mutations, profile, dig, inventory, misc, admin, shop, craft
from handlers.middlewares import EnsureUserMiddleware, SyncBufferMiddleware
from events_scheduler import events_scheduler_loop
from afk_saver import afk_saver_loop

logging.basicConfig(level=logging.INFO)

# На некоторых российских хостингах (в т.ч. иногда на Amvera) исходящий
# доступ к api.telegram.org может блокироваться на уровне провайдера/сети
# (это массовая проблема для РФ-хостов, не специфичная для этого бота — см.
# README). Если видишь в логах постоянные 'Request timeout error' на 60+
# секунд — это оно. Лечится прокси: задай переменную окружения PROXY_URL
# (например "http://user:pass@host:port") в настройках проекта, ничего
# менять в коде не нужно.
PROXY_URL = os.getenv("PROXY_URL")
PREVIEW_HOST = os.getenv("HOST", "0.0.0.0")
PREVIEW_PORT = int(os.getenv("PORT", "3000"))


async def create_fsm_storage():
    """Создаёт хранилище FSM для aiogram.

    Основной режим — RedisStorage. Он выносит состояния пользователей из памяти
    процесса, поэтому они переживают рестарты контейнера и не раздувают RAM бота.
    Если REDIS_URL не задан или Redis временно недоступен, используем безопасный
    fallback на MemoryStorage, чтобы бот не падал при запуске.
    """
    if not REDIS_URL:
        logging.warning("REDIS_URL не задан — FSM будет работать через MemoryStorage.")
        return MemoryStorage()

    try:
        redis = Redis.from_url(REDIS_URL, decode_responses=False)
        await redis.ping()
        logging.info("Redis подключён — FSM работает через RedisStorage.")
        return RedisStorage(
            redis=redis,
            key_builder=DefaultKeyBuilder(with_bot_id=True),
            state_ttl=REDIS_STATE_TTL,
            data_ttl=REDIS_DATA_TTL,
        )
    except Exception as e:
        logging.exception("Не удалось подключиться к Redis, fallback на MemoryStorage: %r", e)
        return MemoryStorage()


async def start_health_server():
    """Мини HTTP healthcheck для sandbox/платформы на 0.0.0.0:3000."""
    async def health(_request):
        return web.json_response({"ok": True, "service": "crab-rpg-bot"})

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, PREVIEW_HOST, PREVIEW_PORT)
    await site.start()
    logging.info("Health server запущен на %s:%s", PREVIEW_HOST, PREVIEW_PORT)
    return runner


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

    health_runner = await start_health_server()
    storage = await create_fsm_storage()
    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)
    dp = Dispatcher(storage=storage)

    # Защита: если FSM-состояние есть, а пользователя в БД нет (например, БД
    # сбросилась при перезапуске контейнера) — мягкий возврат на /start вместо падения
    dp.message.middleware(EnsureUserMiddleware())
    dp.callback_query.middleware(EnsureUserMiddleware())
    
    # Синхронизатор буфера (отложенное сохранение фарма)
    dp.message.middleware(SyncBufferMiddleware())
    dp.callback_query.middleware(SyncBufferMiddleware())

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

    try:
        await _safe_delete_webhook(bot)

        # Фоновый планировщик мифических ивентов — сам стартует/завершает боссов
        asyncio.create_task(events_scheduler_loop(bot))
        
        # Фоновое авто-сохранение AFK-игроков раз в минуту (если доступен Redis)
        if hasattr(storage, 'redis'):
            asyncio.create_task(afk_saver_loop(storage.redis))

        await dp.start_polling(bot)
    finally:
        await health_runner.cleanup()
        await storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
