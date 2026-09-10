# -*- coding: utf-8 -*-
import asyncio
import time
import logging
import database

async def afk_saver_loop(redis):
    """Сохраняет буферы игроков, которые не активны более 3 минут."""
    logging.info("AFK-сейвер запущен.")
    while True:
        try:
            now = int(time.time())
            async for key in redis.scan_iter("user_buffer:*"):
                buffer_data = await redis.hgetall(key)
                if not buffer_data:
                    continue
                    
                last_action = int(buffer_data.get(b"last_action_ts", 0))
                
                # Если прошло 180 секунд (3 минуты) с последнего удара
                if now - last_action >= 180:
                    user_id = int(key.decode("utf-8").split(":")[1])
                    await database.flush_user_buffer(redis, user_id)
                    logging.info(f"Данные AFK-игрока {user_id} успешно сохранены.")
        except Exception as e:
            logging.error(f"Ошибка в AFK-сейвере: {e}")
            
        await asyncio.sleep(60) # Проверяем раз в минуту
