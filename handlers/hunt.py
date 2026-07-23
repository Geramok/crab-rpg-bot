# -*- coding: utf-8 -*-
import json
import random

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

import database
from data import SPECIAL_MUTATIONS
from game_logic import (
    get_effective_stats, next_monster_meters, monster_stats,
    player_attack, monster_attack, gold_reward,
)
from keyboards import hunt_kb
from states import Nav

router = Router()


def _equipped_specials(user_id):
    special = database.get_special_mutations(user_id)
    return {k for k, v in special.items() if v["equipped"]}


@router.message(Nav.hunt, F.text == "🔎 Искать врага")
async def search_enemy(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    stones = database.get_stones(message.from_user.id)
    mutations = database.get_mutations(message.from_user.id)
    stats = get_effective_stats(user, stones, mutations)

    if user["in_hunt"]:
        await message.answer("Ты уже сражаешься! Атакуй или отступи.", reply_markup=hunt_kb(True))
        return

    new_meters = next_monster_meters(user["cur_meters"])
    monster = monster_stats(new_meters)
    monster["poison_turns"] = 0
    monster["poison_dmg"] = 0

    database.update_user(
        message.from_user.id,
        in_hunt=1,
        cur_meters=new_meters,
        cur_hp=stats["max_hp"],
        monster_json=json.dumps(monster),
    )

    await message.answer(
        f"🐟 На {new_meters} м. появился противник!\n"
        f"❤️ Его HP: {monster['hp']}  |  ⚔️ Его урон: {monster['dmg']}\n"
        f"🦀 Твоя прочность: {stats['max_hp']}\n\n"
        f"Жми «⚔️ Атака», чтобы сражаться!",
        reply_markup=hunt_kb(True),
    )


@router.message(Nav.hunt, F.text == "⚔️ Атака")
async def attack(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    if not user["in_hunt"] or not user["monster_json"]:
        await message.answer("Сейчас не с кем сражаться. Нажми «🔎 Искать врага».", reply_markup=hunt_kb(False))
        return

    stones = database.get_stones(message.from_user.id)
    mutations = database.get_mutations(message.from_user.id)
    stats = get_effective_stats(user, stones, mutations)
    specials = _equipped_specials(message.from_user.id)
    original_monster_json = user["monster_json"]
    monster = json.loads(original_monster_json)
    monster.setdefault("poison_turns", 0)
    monster.setdefault("poison_dmg", 0)

    log = []
    cur_hp = user["cur_hp"]  # локально отслеживаем прочность в течение тапа (вампиризм лечит сразу)

    # ☠️ Яд — тикает в начале каждого нового тапа, если наложен
    if monster["poison_turns"] > 0:
        monster["hp"] -= monster["poison_dmg"]
        monster["poison_turns"] -= 1
        log.append(f"☠️ Яд наносит {monster['poison_dmg']} урона. HP врага: {max(monster['hp'], 0)}/{monster['max_hp']}")

    def do_hit(force_crit=False):
        nonlocal cur_hp
        dmg, is_crit = player_attack(stats, force_crit=force_crit)
        monster["hp"] -= dmg
        crit_txt = " 💥КРИТ!" if is_crit else ""
        log.append(f"Ты бьёшь на {dmg}{crit_txt}. HP врага: {max(monster['hp'], 0)}/{monster['max_hp']}")

        if "vampirism" in specials:
            heal = round(dmg * SPECIAL_MUTATIONS["vampirism"]["percent"] / 100)
            if heal > 0:
                cur_hp = min(stats["max_hp"], cur_hp + heal)
                log.append(f"🩸 Вампиризм восстановил {heal} прочности.")

        if "poison" in specials and random.random() * 100 < SPECIAL_MUTATIONS["poison"]["chance"]:
            monster["poison_turns"] = 3
            monster["poison_dmg"] = round(stats["damage"] * 0.3)
            log.append("☠️ Враг отравлен на 3 хода!")

        return is_crit

    force_crit = "puncture" in specials and random.random() * 100 < SPECIAL_MUTATIONS["puncture"]["chance"]
    if force_crit:
        log.append("🗡️ Прокол сработал — гарантированный крит!")
    was_crit = do_hit(force_crit=force_crit)

    # 🌀 Бешенство — после крита шанс на ещё один мгновенный удар
    if monster["hp"] > 0 and was_crit and "frenzy" in specials and random.random() * 100 < SPECIAL_MUTATIONS["frenzy"]["chance"]:
        log.append("🌀 Бешенство! Ещё один удар:")
        do_hit()

    if monster["hp"] <= 0:
        gold = gold_reward(monster, stats)
        if "greed" in specials and random.random() * 100 < SPECIAL_MUTATIONS["greed"]["chance"]:
            gold *= 2
            log.append("🪙 Жадность удвоила добычу золота!")

        new_max_meters = max(user["max_meters"], user["cur_meters"])

        applied = database.try_apply_attack_result(
            message.from_user.id,
            original_monster_json,
            in_hunt=0,
            monster_json=None,
            gold=user["gold"] + gold,
            kills=user["kills"] + 1,
            max_meters=new_max_meters,
            total_earned_gold=user["total_earned_gold"] + gold,
            cur_hp=cur_hp,
        )
        if not applied:
            await message.answer("Слишком быстро — состояние боя уже изменилось, посмотри актуальный статус.", reply_markup=hunt_kb(False))
            return
        log.append(f"🏆 Враг повержен! Получено золота: {gold} 💰")
        await message.answer("\n".join(log), reply_markup=hunt_kb(False))
        return

    # враг атакует в ответ
    mdmg, dodged = monster_attack(monster, stats)
    camouflage_triggered = False
    if not dodged and "camouflage" in specials and random.random() * 100 < SPECIAL_MUTATIONS["camouflage"]["chance"]:
        dodged = True
        mdmg = 0
        camouflage_triggered = True

    new_hp = cur_hp - mdmg
    if dodged:
        if camouflage_triggered:
            log.append("🌊 Маскировка полностью скрыла тебя от удара!")
        else:
            log.append("Ты уклонился от удара врага! 🌊")
    else:
        log.append(f"Враг бьёт тебя на {mdmg}. Твоя прочность: {max(new_hp, 0)}/{stats['max_hp']}")

    if new_hp <= 0:
        applied = database.try_apply_attack_result(
            message.from_user.id,
            original_monster_json,
            in_hunt=0,
            monster_json=None,
            cur_hp=0,
            cur_meters=0,
        )
        if not applied:
            await message.answer("Слишком быстро — состояние боя уже изменилось, посмотри актуальный статус.", reply_markup=hunt_kb(False))
            return
        log.append("💔 Твой панцирь не выдержал! Ты отступаешь на берег зализывать раны...")
        await message.answer("\n".join(log), reply_markup=hunt_kb(False))
        return

    applied = database.try_apply_attack_result(
        message.from_user.id,
        original_monster_json,
        cur_hp=new_hp,
        monster_json=json.dumps(monster),
    )
    if not applied:
        await message.answer("Слишком быстро — состояние боя уже изменилось, посмотри актуальный статус.", reply_markup=hunt_kb(True))
        return
    await message.answer("\n".join(log), reply_markup=hunt_kb(True))


@router.message(Nav.hunt, F.text == "🏃 Отступить")
async def retreat(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    if user["in_hunt"]:
        database.update_user(message.from_user.id, in_hunt=0, monster_json=None)
    await message.answer(
        "Ты отступаешь, сохранив свою позицию. Можешь вернуться на охоту в любой момент.",
        reply_markup=hunt_kb(False),
    )
