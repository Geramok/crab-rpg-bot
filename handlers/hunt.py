# -*- coding: utf-8 -*-
import json
import random
import time

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import SPECIAL_MUTATIONS
from game_logic import (
    get_effective_stats, next_monster_meters, roll_monster, is_guard_camp_meter,
    roll_guard_camp, player_attack, monster_attack, gold_reward, apply_idle_regen,
    defeat_knockback_meters, roll_kill_resource,
)
from keyboards import hunt_kb
from states import Nav

router = Router()


def _equipped_specials(user_id):
    special = database.get_special_mutations(user_id)
    return {k for k, v in special.items() if v["equipped"]}


def _hp_bar(current, total, length=10):
    current = max(0, current)
    total = max(1, total)
    filled = max(0, min(length, round(length * current / total)))
    return "█" * filled + "░" * (length - filled)


def _render_single(user_cur_hp, stats_max_hp, monster, last_line=None):
    text = (
        f"<pre>{monster['art']}</pre>\n"
        f"<b>{monster['name']}</b>\n"
        f"❤️ Враг:  [{_hp_bar(monster['hp'], monster['max_hp'])}] {max(monster['hp'],0)}/{monster['max_hp']}\n"
        f"🦀 Ты:    [{_hp_bar(user_cur_hp, stats_max_hp)}] {max(user_cur_hp,0)}/{stats_max_hp}\n"
    )
    if last_line:
        text += f"\n{last_line}"
    return text


def _render_camp(user_cur_hp, stats_max_hp, camp, last_line=None):
    text = "🛡️ <b>Засада стражей!</b> Золото — только за полную зачистку всех троих.\n\n"
    buttons = []
    for i, guard in enumerate(camp["guards"]):
        mark = "💀" if camp["defeated"][i] else ("👉" if i == camp["current"] else "  ")
        status = "повержен" if camp["defeated"][i] else f"{max(guard['hp'],0)}/{guard['max_hp']} HP"
        text += f"{mark} {guard['name']} — {status}\n"
        if not camp["defeated"][i]:
            buttons.append([InlineKeyboardButton(text=f"🎯 Бить: {guard['name']}", callback_data=f"pick_guard_{i}")])
    current_guard = camp["guards"][camp["current"]]
    text += f"\n<pre>{current_guard['art']}</pre>\n"
    text += f"🦀 Ты: [{_hp_bar(user_cur_hp, stats_max_hp)}] {max(user_cur_hp,0)}/{stats_max_hp}\n"
    if last_line:
        text += f"\n{last_line}"
    return text, InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


async def _push_battle_update(message, user_id, message_id, text, reply_markup=None):
    """Обновляет боевой экран. Сначала пробует отредактировать существующее
    сообщение; если Telegram отклонил правку (флуд-контроль при частых тапах,
    сообщение устарело/удалено и т.п.) — просто шлёт новое сообщение вместо
    того, чтобы молча падать (из-за чего раньше бой мог 'зависать' без ответа).
    Возвращает актуальный message_id боевого экрана."""
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id, message_id=message_id, text=text, reply_markup=reply_markup
        )
        return message_id
    except Exception:
        sent = await message.answer(text, reply_markup=reply_markup)
        database.update_user(user_id, battle_message_id=sent.message_id)
        return sent.message_id


@router.message(Nav.hunt, F.text == "🔎 Рыскать по дну")
async def search_enemy(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    if user["in_hunt"]:
        await message.answer("Ты уже сражаешься! Атакуй или отступи.", reply_markup=hunt_kb(True))
        return

    stones = database.get_stones(message.from_user.id)
    mutations = database.get_mutations(message.from_user.id)
    stats = get_effective_stats(user, stones, mutations)

    now = int(time.time())
    healed_hp = apply_idle_regen(user, stats, now)

    new_meters = next_monster_meters(user["cur_meters"])

    if is_guard_camp_meter(user["cur_meters"], new_meters):
        guards = roll_guard_camp(new_meters)
        camp = {
            "is_camp": True, "meters": new_meters, "guards": guards,
            "defeated": [False, False, False], "current": 0,
        }
        monster_json = json.dumps(camp)
        text, ikb = _render_camp(healed_hp, stats["max_hp"], camp)
    else:
        monster = roll_monster(new_meters)
        monster["meters"] = new_meters
        monster_json = json.dumps(monster)
        text, ikb = _render_single(healed_hp, stats["max_hp"], monster), None

    # Сначала обновляем нижнюю клавиатуру (Атака/Отступить) — это отдельное
    # сообщение по требованию Telegram (нельзя одновременно сменить reply-клавиатуру
    # и прикрепить инлайн-кнопки к одному сообщению).
    sent = await message.answer(text, reply_markup=hunt_kb(True))
    database.update_user(
        message.from_user.id,
        in_hunt=1, monster_json=monster_json, cur_hp=healed_hp,
        last_hp_regen_ts=now, battle_message_id=sent.message_id,
    )
    if ikb:
        await _push_battle_update(message, message.from_user.id, sent.message_id, text, ikb)


@router.callback_query(F.data.startswith("pick_guard_"))
async def pick_guard(call: CallbackQuery):
    idx = int(call.data.split("_")[-1])
    user = database.get_user(call.from_user.id)
    if not user["in_hunt"] or not user["monster_json"]:
        await call.answer()
        return
    camp = json.loads(user["monster_json"])
    if not camp.get("is_camp") or camp["defeated"][idx]:
        await call.answer("Этот страж уже повержен.", show_alert=True)
        return
    camp["current"] = idx
    database.update_user(call.from_user.id, monster_json=json.dumps(camp))

    stones = database.get_stones(call.from_user.id)
    mutations = database.get_mutations(call.from_user.id)
    stats = get_effective_stats(user, stones, mutations)
    text, ikb = _render_camp(user["cur_hp"], stats["max_hp"], camp)
    await call.answer()
    try:
        await call.message.edit_text(text, reply_markup=ikb)
    except Exception:
        sent = await call.message.answer(text, reply_markup=ikb)
        database.update_user(call.from_user.id, battle_message_id=sent.message_id)


def _do_combat_round(target, stats, specials, log):
    """Одна серия ударов игрока по target (моб или страж). Возвращает исцеление от вампиризма."""
    def do_hit(force_crit=False):
        dmg, is_crit, missed = player_attack(stats, monster_evasion=target["evasion"], force_crit=force_crit)
        if missed:
            log.append("💨 Промах!")
            return False
        target["hp"] -= dmg
        crit_txt = " 💥" if is_crit else ""
        log.append(f"Удар: -{dmg}{crit_txt}")
        if "vampirism" in specials:
            heal = round(dmg * SPECIAL_MUTATIONS["vampirism"]["percent"] / 100)
            if heal > 0:
                log.append(f"🩸 +{heal} HP")
                do_hit.heal = do_hit.__dict__.get("heal", 0) + heal
        if "poison" in specials and random.random() * 100 < SPECIAL_MUTATIONS["poison"]["chance"]:
            target["poison_turns"] = 3
            target["poison_dmg"] = round(stats["damage"] * 0.3)
            log.append("☠️ Отравлен!")
        return is_crit

    do_hit.heal = 0

    if target.get("poison_turns", 0) > 0:
        target["hp"] -= target["poison_dmg"]
        target["poison_turns"] -= 1
        log.append(f"☠️ Яд: -{target['poison_dmg']}")

    force_crit = "puncture" in specials and random.random() * 100 < SPECIAL_MUTATIONS["puncture"]["chance"]
    was_crit = do_hit(force_crit=force_crit)

    if target["hp"] > 0 and was_crit and "frenzy" in specials and random.random() * 100 < SPECIAL_MUTATIONS["frenzy"]["chance"]:
        log.append("🌀 Бешенство!")
        do_hit()

    return do_hit.heal


@router.message(Nav.hunt, F.text == "⚔️ Атака")
async def attack(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    if not user["in_hunt"] or not user["monster_json"]:
        await message.answer("Сейчас не с кем сражаться. Нажми «🔎 Рыскать по дну».", reply_markup=hunt_kb(False))
        return

    stones = database.get_stones(message.from_user.id)
    mutations = database.get_mutations(message.from_user.id)
    stats = get_effective_stats(user, stones, mutations)
    specials = _equipped_specials(message.from_user.id)
    original_monster_json = user["monster_json"]
    data = json.loads(original_monster_json)
    is_camp = data.get("is_camp", False)
    target = data["guards"][data["current"]] if is_camp else data

    log = []
    cur_hp = user["cur_hp"]
    heal = _do_combat_round(target, stats, specials, log)
    cur_hp = min(stats["max_hp"], cur_hp + heal)

    if target["hp"] <= 0:
        resource = roll_kill_resource()
        if is_camp:
            data["defeated"][data["current"]] = True
            remaining = [i for i, d in enumerate(data["defeated"]) if not d]
            if remaining:
                data["current"] = remaining[0]
                text, ikb = _render_camp(cur_hp, stats["max_hp"], data, last_line="\n".join(log) + "\n\n🎯 Выбери следующую цель.")
                applied = database.try_apply_attack_result(
                    message.from_user.id, original_monster_json,
                    monster_json=json.dumps(data), cur_hp=cur_hp,
                )
                if not applied:
                    return
                await _push_battle_update(message, message.from_user.id, user["battle_message_id"], text, ikb)
                return
            total_gold = sum(gold_reward(g, stats, user) for g in data["guards"])
            new_max_meters = max(user["max_meters"], data["meters"])
            applied = database.try_apply_attack_result(
                message.from_user.id, original_monster_json,
                in_hunt=0, monster_json=None, cur_hp=cur_hp,
                gold=user["gold"] + total_gold, kills=user["kills"] + 3,
                cur_meters=data["meters"], max_meters=new_max_meters,
                total_earned_gold=user["total_earned_gold"] + total_gold,
                last_hp_regen_ts=int(time.time()),
            )
            if not applied:
                return
            if resource:
                database.add_resource(message.from_user.id, resource)
            final_text = "🏆 <b>Засада зачищена!</b>\n" + "\n".join(log) + f"\n\n💰 Получено золота за всех троих: {total_gold}"
            await _push_battle_update(message, message.from_user.id, user["battle_message_id"], final_text)
            await message.answer("Готов к новому рысканью по дну.", reply_markup=hunt_kb(False))
            return

        gold = gold_reward(data, stats, user)
        new_max_meters = max(user["max_meters"], data["meters"])
        applied = database.try_apply_attack_result(
            message.from_user.id, original_monster_json,
            in_hunt=0, monster_json=None, cur_hp=cur_hp,
            gold=user["gold"] + gold, kills=user["kills"] + 1,
            cur_meters=data["meters"], max_meters=new_max_meters,
            total_earned_gold=user["total_earned_gold"] + gold,
            last_hp_regen_ts=int(time.time()),
        )
        if not applied:
            return
        if resource:
            database.add_resource(message.from_user.id, resource)
        final_text = "🏆 <b>Победа!</b>\n" + "\n".join(log) + f"\n\n💰 Золото: {gold}"
        await _push_battle_update(message, message.from_user.id, user["battle_message_id"], final_text)
        await message.answer("Готов к новому рысканью по дну.", reply_markup=hunt_kb(False))
        return

    mdmg, dodged = monster_attack(target, stats)
    camouflage_triggered = False
    if not dodged and "camouflage" in specials and random.random() * 100 < SPECIAL_MUTATIONS["camouflage"]["chance"]:
        dodged, mdmg, camouflage_triggered = True, 0, True

    new_hp = cur_hp - mdmg
    if dodged:
        log.append("🌊 Уклонился!" if not camouflage_triggered else "🌊 Маскировка спасла!")
    else:
        log.append(f"Враг бьёт: -{mdmg}")

    last_line = "\n".join(log)

    if new_hp <= 0:
        knock_to = defeat_knockback_meters(user["cur_meters"])
        recovered_hp = stats["max_hp"]
        applied = database.try_apply_attack_result(
            message.from_user.id, original_monster_json,
            in_hunt=0, monster_json=None, cur_hp=recovered_hp,
            cur_meters=knock_to, last_hp_regen_ts=int(time.time()),
        )
        if not applied:
            return
        final_text = (
            f"💔 <b>Панцирь треснул!</b> Тебя отбросило с позиции {user['cur_meters']} м. "
            f"назад до {knock_to} м.\nПрочность восстановлена полностью — можешь пробовать снова прямо сейчас.\n\n"
            + last_line
        )
        await _push_battle_update(message, message.from_user.id, user["battle_message_id"], final_text)
        await message.answer("Можешь продолжать рыскать по дну.", reply_markup=hunt_kb(False))
        return

    if is_camp:
        text, ikb = _render_camp(new_hp, stats["max_hp"], data, last_line=last_line)
    else:
        text, ikb = _render_single(new_hp, stats["max_hp"], data, last_line=last_line), None

    applied = database.try_apply_attack_result(
        message.from_user.id, original_monster_json,
        cur_hp=new_hp, monster_json=json.dumps(data),
    )
    if not applied:
        return
    await _push_battle_update(message, message.from_user.id, user["battle_message_id"], text, ikb)


@router.message(Nav.hunt, F.text == "🏃 Отступить")
async def retreat(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    if user["in_hunt"]:
        database.update_user(
            message.from_user.id, in_hunt=0, monster_json=None,
            last_hp_regen_ts=int(time.time()),
        )
        if user["battle_message_id"]:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id, message_id=user["battle_message_id"],
                    text="🏃 Ты отступил, сохранив позицию и текущую прочность. Награды не будет.",
                )
            except Exception:
                pass
    await message.answer(
        "Отступление сохраняет позицию и прочность как есть — прочность сама восстановится "
        "со временем, если не охотиться. Награда за отменённый бой не начисляется.",
        reply_markup=hunt_kb(False),
    )
