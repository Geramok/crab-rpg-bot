# -*- coding: utf-8 -*-
"""
Логика завершения ивента и раздачи наград. 
Раздает сундуки в зависимости от места по нанесенному урону.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import database
from data import EVENT_CHESTS

MIN_DAMAGE_THRESHOLD = 30  # отсекаем случайные 1 клик мимо

async def finish_event(bot, event):
    participants = await database.run_async(database.get_all_event_participants, event["id"])
    await database.run_async(database.close_event, event["id"])

    qualified = [p for p in participants if p["damage"] >= MIN_DAMAGE_THRESHOLD]

    if not qualified:
        return []

    # Сортируем участников по урону (от большего к меньшему) для распределения мест
    qualified.sort(key=lambda x: x["damage"], reverse=True)

    results = []
    for rank, p in enumerate(qualified, start=1):
        uid = p["user_id"]
        user = await database.run_async(database.get_user, uid)
        if not user:
            continue

        # Увеличиваем счетчик убитых боссов
        await database.run_async(
            database.update_user, uid,
            boss_kills=user["boss_kills"] + 1
        )

        # Определяем редкость сундука по месту в топе
        if rank == 1:
            chest_type = 1  # Жемчужный
        elif rank == 2:
            chest_type = 2  # Золотой
        elif rank == 3:
            chest_type = 3  # Роскошный
        else:
            chest_type = "default"  # Старый сундук для всех остальных

        chest_data = EVENT_CHESTS[chest_type]

        # Выдаем сундук в инвентарь (в базу данных)
        await database.run_async(database.add_chest, uid, chest_type, 1)
        results.append((uid, chest_type))

        # Создаем инлайн-кнопку для открытия сундука
        ikb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Открыть сундук", callback_data=f"open_chest_{chest_type}")]
        ])

        place_text = f"Ты занял <b>{rank}-е место</b> по урону!" if rank <= 3 else "Ты достойно сражался наравне со всеми!"
        msg_text = (
            f"🎉 Ивент «{event['name']}» завершён!\n"
            f"{place_text}\n\n"
            f"Среди кораллов и обломков панциря босса ты замечаешь странный предмет... "
            f"Это <b>{chest_data['name']}</b>!"
        )

        try:
            await bot.send_message(uid, msg_text, reply_markup=ikb)
        except Exception:
            pass

    return results
