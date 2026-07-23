# -*- coding: utf-8 -*-
import asyncio
import logging
import random
import time

import database
from data import MYTHIC_EVENTS, MYTHIC_EVENT_DURATION_HOURS, MYTHIC_EVENT_CHECK_INTERVAL_SECONDS
from events_logic import finish_event

logger = logging.getLogger(__name__)


async def events_scheduler_loop(bot):
    """Раз в MYTHIC_EVENT_CHECK_INTERVAL_SECONDS проверяет: если текущий ивент
    закончился по времени — раздаёт награды и закрывает его; если активного
    ивента нет — запускает случайный мифический ивент сам, без участия админа."""
    while True:
        try:
            event = database.get_active_event()
            now = int(time.time())

            if event and event["ends_at"] <= now:
                logger.info(f"Автозавершение ивента: {event['name']}")
                await finish_event(bot, event)
                event = None

            if not event:
                template = random.choice(MYTHIC_EVENTS)
                event_id = database.create_event(
                    template["name"], template["description"],
                    MYTHIC_EVENT_DURATION_HOURS * 3600,
                )
                logger.info(f"Автозапуск нового мифического ивента: {template['name']} (id={event_id})")
        except Exception:
            logger.exception("Ошибка в цикле планировщика ивентов")

        await asyncio.sleep(MYTHIC_EVENT_CHECK_INTERVAL_SECONDS)
