# -*- coding: utf-8 -*-
"""
Логика завершения ивента и раздачи наград. Используется и из ручной админ-команды
/endboss, и из автоматического планировщика ивентов (bot.py).

Важно: награды раздаются НЕ строго топовым игрокам по урону, а через взвешенную
лотерею (вес = корень из урона) — так шанс получить редкую мутацию есть у любого,
кто реально участвовал, а не только у задротов с самым большим уроном.
"""
import math
import random

import database
from data import STONE_COLORS, SPECIAL_MUTATIONS

MIN_DAMAGE_THRESHOLD = 30  # отсекаем случайные 1 клик мимо, но не более того


async def finish_event(bot, event):
    participants = await database.run_async(database.get_all_event_participants, event["id"])
    await database.run_async(database.close_event, event["id"])

    qualified = [p for p in participants if p["damage"] >= MIN_DAMAGE_THRESHOLD]

    if not qualified:
        return []

    # Всем, кто реально участвовал, — гарантированная базовая награда (раковины + камень)
    for p in qualified:
        uid = p["user_id"]
        user = await database.run_async(database.get_user, uid)
        if not user:
            continue
        await database.run_async(
            database.update_user, uid,
            boss_kills=user["boss_kills"] + 1, nautilus_shells=user["nautilus_shells"] + 2,
        )
        color = random.choice(list(STONE_COLORS.keys()))
        await database.run_async(database.add_stone, uid, color, 1, 1)

    # Жемчужные кейсы (особые мутации) — честная лотерея с весом sqrt(урон), чтобы
    # не только топ по урону имел шанс, но и активные игроки послабее
    cases_count = max(1, round(len(qualified) * 0.35))
    ids = [p["user_id"] for p in qualified]
    weights = [math.sqrt(p["damage"]) for p in qualified]
    winners = database_weighted_pick(ids, weights, cases_count)

    results = []
    for uid in winners:
        user = await database.run_async(database.get_user, uid)
        if not user:
            continue
        special = random.choice(list(SPECIAL_MUTATIONS.keys()))
        await database.run_async(database.add_special_mutation, uid, special)
        await database.run_async(database.update_user, uid, nautilus_shells=user["nautilus_shells"] + 5)
        results.append((uid, special))

        try:
            await bot.send_message(
                uid,
                f"🎉 Ивент «{event['name']}» завершён! Тебе выпал жемчужный кейс — "
                f"новая мутация «{SPECIAL_MUTATIONS[special]['name']}» уже в твоём инвентаре!",
            )
        except Exception:
            pass

    # Уведомляем остальных участников без кейса — просто про базовые награды
    winner_ids = {uid for uid, _ in results}
    for p in qualified:
        uid = p["user_id"]
        if uid in winner_ids:
            continue
        try:
            await bot.send_message(
                uid,
                f"🐉 Ивент «{event['name']}» завершён. Спасибо за участие! "
                f"Награда за участие (раковины и камень) уже у тебя в инвентаре.",
            )
        except Exception:
            pass

    return results


def database_weighted_pick(ids, weights, k):
    from game_logic import weighted_sample_without_replacement
    return weighted_sample_without_replacement(ids, weights, k)
