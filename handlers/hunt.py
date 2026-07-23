# -*- coding: utf-8 -*-
import json

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

import database
from game_logic import (
    get_effective_stats, next_monster_meters, monster_stats,
    player_attack, monster_attack, gold_reward,
)
from keyboards import hunt_kb
from states import Nav

router = Router()


def _load_user_stats(user_id):
    user = database.get_user(user_id)
    mutations = database.get_mutations(user_id)
    stones = database.get_stones(user_id)
    stats = get_effective_stats(user, mutations, stones)
    return user, stats


@router.message(Nav.hunt, F.text == "🔎 Искать врага")
async def search_enemy(message: Message, state: FSMContext):
    user, stats = _load_user_stats(message.from_user.id)

    if user["in_hunt"]:
        await message.answer("Ты уже сражаешься! Атакуй или отступи.", reply_markup=hunt_kb(True))
        return

    new_meters = next_monster_meters(user["cur_meters"])
    monster = monster_stats(new_meters)

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

    mutations = database.get_mutations(message.from_user.id)
    stones = database.get_stones(message.from_user.id)
    stats = get_effective_stats(user, mutations, stones)
    monster = json.loads(user["monster_json"])

    dmg, is_crit = player_attack(stats)
    monster["hp"] -= dmg
    crit_txt = " 💥КРИТ!" if is_crit else ""
    log = [f"Ты бьёшь на {dmg}{crit_txt}. HP врага: {max(monster['hp'], 0)}/{monster['max_hp']}"]

    if monster["hp"] <= 0:
        gold = gold_reward(monster, stats)
        new_max_meters = max(user["max_meters"], user["cur_meters"])
        database.update_user(
            message.from_user.id,
            in_hunt=0,
            monster_json=None,
            gold=user["gold"] + gold,
            kills=user["kills"] + 1,
            max_meters=new_max_meters,
            total_earned_gold=user["total_earned_gold"] + gold,
        )
        log.append(f"🏆 Враг повержен! Получено золота: {gold} 💰")
        await message.answer("\n".join(log), reply_markup=hunt_kb(False))
        return

    # враг атакует в ответ
    mdmg, dodged = monster_attack(monster, stats)
    new_hp = user["cur_hp"] - mdmg
    if dodged:
        log.append("Ты уклонился от удара врага! 🌊")
    else:
        log.append(f"Враг бьёт тебя на {mdmg}. Твоя прочность: {max(new_hp, 0)}/{stats['max_hp']}")

    if new_hp <= 0:
        database.update_user(
            message.from_user.id,
            in_hunt=0,
            monster_json=None,
            cur_hp=0,
            cur_meters=0,
        )
        log.append("💔 Твой панцирь не выдержал! Ты отступаешь на берег зализывать раны...")
        await message.answer("\n".join(log), reply_markup=hunt_kb(False))
        return

    database.update_user(
        message.from_user.id,
        cur_hp=new_hp,
        monster_json=json.dumps(monster),
    )
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
