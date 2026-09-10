# -*- coding: utf-8 -*-
import html
import json
import random
import time

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import SHIELD_ABILITY, MARK_ABILITY, UNIQUE_ABILITIES
from game_logic import (
    get_effective_stats, next_monster_meters, roll_monster, is_elite_encounter_meter,
    player_attack, monster_attack, gold_reward, apply_idle_regen,
    defeat_knockback_meters, roll_kill_resource, get_blocking_barrier, total_mutation_levels,
    ELITE_ENCOUNTER_MULT, format_number, get_equipped_special_effects
)
from keyboards import hunt_kb
from states import Nav

router = Router()

ATTACK_BUTTON = InlineKeyboardButton(text="✂️ Клешнёй!", callback_data="hunt_attack")

DEFAULT_ABILITIES_STATE = {
    "shield_cooldown": 0,
    "mark_used": False,
    "mark_active": False,
    "mark_miss_turns": 0,
    "mark_bonus_earned": False,
    "mark_bonus_guard_index": None,
    "unique_used": False,
    "sprint_turns": 0,
    "fatigue_turns": 0,
    "rage_active": False,
}

def _get_abilities(data):
    ab = data.get("abilities")
    if ab is None:
        ab = DEFAULT_ABILITIES_STATE.copy()
        data["abilities"] = ab
    else:
        for key, default_value in DEFAULT_ABILITIES_STATE.items():
            ab.setdefault(key, default_value)
    return ab

def _tick_ability_timers(abilities, consumed_sprint=False, consumed_mark_miss=False):
    if abilities["shield_cooldown"] > 0:
        abilities["shield_cooldown"] -= 1
    if abilities["fatigue_turns"] > 0 and not consumed_sprint:
        abilities["fatigue_turns"] -= 1

def _hp_bar(current, total, length=10):
    current = max(0, current)
    total = max(1, total)
    filled = max(0, min(length, round(length * current / total)))
    return "█" * filled + "░" * (length - filled)

def _abilities_status_line(abilities, crab_type):
    parts = []
    if abilities["sprint_turns"] > 0:
        parts.append(f"💨 Рывок: ещё {abilities['sprint_turns']} х.")
    if abilities["fatigue_turns"] > 0:
        parts.append(f"😮‍💨 Устал: ещё {abilities['fatigue_turns']} х.")
    if abilities["rage_active"]:
        parts.append("🩸 Раж активен")
    
    if abilities["mark_active"] and abilities["mark_miss_turns"] > 0:
        parts.append(f"🪝 Проклятие: ещё {abilities['mark_miss_turns']} промах(а)")
    elif abilities["mark_active"]:
        parts.append("🪝 Проклятие активно")
        
    return " | ".join(parts)

def _abilities_buttons(abilities, crab_type):
    shield_name = SHIELD_ABILITY["name"]
    shield_label = shield_name if abilities["shield_cooldown"] <= 0 else f"{shield_name} ({abilities['shield_cooldown']})"
    
    mark_label = "🪝 Проклятие" if not abilities["mark_used"] else "🪝 Проклятие (исп.)"
    
    unique = UNIQUE_ABILITIES.get(crab_type, UNIQUE_ABILITIES[1])
    unique_label = unique["name"] if not abilities["unique_used"] else f"{unique['name']} (использована)"
    return [
        [
            InlineKeyboardButton(text=shield_label, callback_data="ability_shield"),
            InlineKeyboardButton(text=mark_label, callback_data="ability_mark"),
        ],
        [InlineKeyboardButton(text=unique_label, callback_data="ability_unique")],
    ]

def _render_single(user_cur_hp, stats_max_hp, monster, crab_type, last_line=None):
    if monster.get("is_boss"):
        text = (
            f"<pre>{html.escape(monster['art'])}</pre>\n"
            f"🐉 <b>{monster['name']}</b>\n"
            f"{monster['hp_flavor']}\n"
            f"💥 Нанесено урона: <b>{format_number(monster.get('accumulated_damage', 0))}</b>\n\n"
            f"🦀 Ты:  [{_hp_bar(user_cur_hp, stats_max_hp)}] {format_number(max(user_cur_hp, 0))}/{format_number(stats_max_hp)}\n"
        )
        if last_line:
            text += f"\n{last_line}"
        buttons = [[ATTACK_BUTTON]]
        return text, InlineKeyboardMarkup(inline_keyboard=buttons)

    abilities = _get_abilities(monster)
    name_line = f"💪 <b>{monster['name']} (усилен)</b>" if monster.get("elite") else f"<b>{monster['name']}</b>"
    text = (
        f"<pre>{html.escape(monster['art'])}</pre>\n"
        f"{name_line}\n"
        f"❤️ Враг:  [{_hp_bar(monster['hp'], monster['max_hp'])}] {format_number(max(monster['hp'], 0))}/{format_number(monster['max_hp'])}\n"
        f"🦀 Ты:    [{_hp_bar(user_cur_hp, stats_max_hp)}] {format_number(max(user_cur_hp, 0))}/{format_number(stats_max_hp)}\n"
    )
    status = _abilities_status_line(abilities, crab_type)
    if status:
        text += f"{status}\n"
    if last_line:
        text += f"\n{last_line}"
    buttons = [[ATTACK_BUTTON]] + _abilities_buttons(abilities, crab_type)
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)

def _render_camp(user_cur_hp, stats_max_hp, camp, crab_type, last_line=None):
    abilities = _get_abilities(camp)
    text = "🛡️ <b>Засада стражей!</b> Золото — только за полную зачистку всех троих.\n\n"
    buttons = []
    for i, guard in enumerate(camp["guards"]):
        mark = "💀" if camp["defeated"][i] else ("👉" if i == camp["current"] else "  ")
        status = "повержен" if camp["defeated"][i] else f"{format_number(max(guard['hp'], 0))}/{format_number(guard['max_hp'])} HP"
        text += f"{mark} {guard['name']} — {status}\n"
        if not camp["defeated"][i]:
            btn_text = f"🎯 {'Бить' if i == camp['current'] else 'Переключиться на'}: {guard['name']}"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"pick_guard_{i}")])
    current_guard = camp["guards"][camp["current"]]
    text += f"\n<pre>{html.escape(current_guard['art'])}</pre>\n"
    text += f"🦀 Ты: [{_hp_bar(user_cur_hp, stats_max_hp)}] {format_number(max(user_cur_hp, 0))}/{format_number(stats_max_hp)}\n"
    ab_status = _abilities_status_line(abilities, crab_type)
    if ab_status:
        text += f"{ab_status}\n"
    if last_line:
        text += f"\n{last_line}"
    buttons.append([ATTACK_BUTTON])
    buttons += _abilities_buttons(abilities, crab_type)
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)

async def _push_battle_update(message, user_id, message_id, text, reply_markup=None):
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id, message_id=message_id, text=text, reply_markup=reply_markup
        )
        return message_id
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return message_id
        sent = await message.answer(text, reply_markup=reply_markup)
        await database.run_async(database.update_user, user_id, battle_message_id=sent.message_id)
        return sent.message_id
    except Exception:
        sent = await message.answer(text, reply_markup=reply_markup)
        await database.run_async(database.update_user, user_id, battle_message_id=sent.message_id)
        return sent.message_id

async def perform_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await database.run_async(database.get_user, user_id)
    stones = await database.run_async(database.get_stones, user_id)
    mutations = await database.run_async(database.get_mutations_v2, user_id)
    stats = get_effective_stats(user, stones, mutations)
    now = int(time.time())
    healed_hp = apply_idle_regen(user, stats, now)
    crab_type = user["crab_type"]

    new_meters = next_monster_meters(user["cur_meters"], mutations)
    barrier = get_blocking_barrier(new_meters, mutations)
    barrier_line = None
    if barrier:
        barrier_meters, required = barrier
        have = total_mutation_levels(mutations)
        barrier_line = (
            f"🚧 <b>Стена прокачки на {format_number(barrier_meters)}м!</b> Нужно суммарно {required} "
            f"уровней мутаций (сейчас {have}) — дальше не пройти, пока не прокачаешься "
            f"в разделе «⚔️ Мощь» → «🧪 Мутации»."
        )

    is_elite = is_elite_encounter_meter(user["cur_meters"], new_meters)
    monster = roll_monster(new_meters, elite_mult=ELITE_ENCOUNTER_MULT if is_elite else 1.0)
    monster["meters"] = new_meters
    monster["elite"] = is_elite
    monster_json = json.dumps(monster)
    text, ikb = _render_single(healed_hp, stats["max_hp"], monster, crab_type)

    if barrier_line:
        text = f"{barrier_line}\n\n{text}"

    started = await database.run_async(database.try_start_new_hunt, user_id, monster_json, healed_hp, now)

    if not started:
        current = await database.run_async(database.get_user, user_id)
        if current["in_hunt"] and current["monster_json"]:
            data = json.loads(current["monster_json"])
            if data.get("is_camp"):
                cur_text, cur_ikb = _render_camp(current["cur_hp"], stats["max_hp"], data, crab_type)
            else:
                cur_text, cur_ikb = _render_single(current["cur_hp"], stats["max_hp"], data, crab_type)
            if current["battle_message_id"]:
                await _push_battle_update(
                    message, user_id, current["battle_message_id"], cur_text, cur_ikb
                )
            else:
                await message.answer("⚔️ Возвращаемся в бой...", reply_markup=hunt_kb(True))
                sent = await message.answer(cur_text, reply_markup=cur_ikb)
                await database.run_async(database.update_user, user_id, battle_message_id=sent.message_id)
            return

        await database.run_async(database.update_user, user_id, in_hunt=0, monster_json=None)
        started = await database.run_async(database.try_start_new_hunt, user_id, monster_json, healed_hp, now)

    if not started:
        fresh = await database.run_async(database.get_user, user_id)
        await message.answer("Секунду...", reply_markup=hunt_kb(bool(fresh["in_hunt"])))
        return

    try:
        await message.answer("🫧 Вглядываемся в муть...", reply_markup=hunt_kb(True))
        sent = await message.answer(text, reply_markup=ikb)
        await database.run_async(database.update_user, user_id, battle_message_id=sent.message_id)
        
        # Сохраняем все данные в быструю память Redis!
        fsm_data = {
            "cur_hp": healed_hp,
            "stats": stats,
            "specials": list(get_equipped_special_effects(mutations)),
            "crab_type": crab_type,
            "cur_meters": user["cur_meters"],
            "max_meters": user["max_meters"],
            "monster": monster,
            "abilities": _get_abilities(monster),
            "original_monster_json": monster_json,
            "battle_message_id": sent.message_id
        }
        await state.update_data(**fsm_data)

    except Exception:
        await database.run_async(database.update_user, user_id, in_hunt=0, monster_json=None)
        raise

@router.message(StateFilter(Nav.hunt, Nav.main, None), F.text.contains("Рыскать по дну"))
async def search_enemy(message: Message, state: FSMContext):
    await state.set_state(Nav.hunt)
    await perform_search(message, state)


async def _load_battle_context(user_id, state: FSMContext):
    """
    Умная загрузка: берет бой из быстрой памяти Redis. 
    Если данных там нет (бой запущен из админки или Redis сбросился), подтягивает из SQLite.
    """
    data = await state.get_data()
    
    if "monster" not in data:
        user = await database.run_async(database.get_user, user_id)
        if not user["in_hunt"] or not user["monster_json"]:
            return None
            
        stones = await database.run_async(database.get_stones, user_id)
        mutations = await database.run_async(database.get_mutations_v2, user_id)
        stats = get_effective_stats(user, stones, mutations)
        specials = list(get_equipped_special_effects(mutations))
        
        monster_data = json.loads(user["monster_json"])
        abilities = _get_abilities(monster_data)
        
        data = {
            "cur_hp": user["cur_hp"],
            "stats": stats,
            "specials": specials,
            "crab_type": user["crab_type"],
            "cur_meters": user["cur_meters"],
            "max_meters": user["max_meters"],
            "monster": monster_data,
            "abilities": abilities,
            "original_monster_json": user["monster_json"],
            "battle_message_id": user["battle_message_id"]
        }
        await state.update_data(**data)

    is_camp = data["monster"].get("is_camp", False)
    target = data["monster"]["guards"][data["monster"]["current"]] if is_camp else data["monster"]
    return data, is_camp, target


@router.callback_query(F.data.startswith("pick_guard_"))
async def pick_guard(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split("_")[-1])
    ctx = await _load_battle_context(call.from_user.id, state)
    if not ctx:
        await call.answer()
        return
        
    data, is_camp, target = ctx
    camp = data["monster"]
    
    if not camp.get("is_camp") or camp["defeated"][idx]:
        await call.answer("Этот страж уже повержен.", show_alert=True)
        return
        
    # Моментальное обновление в Redis без SQLite
    camp["current"] = idx
    await state.update_data(monster=camp)

    text, ikb = _render_camp(data["cur_hp"], data["stats"]["max_hp"], camp, data["crab_type"])
    await call.answer()
    await _push_battle_update(call.message, call.from_user.id, data.get("battle_message_id", call.message.message_id), text, ikb)


def _do_combat_round(target, stats, specials, log, force_crit=False, guaranteed_hit=False,
                     guaranteed_miss=False, dmg_multiplier=1.0, extra_miss_chance=0):
    def do_hit(force_crit=force_crit):
        if guaranteed_miss:
            log.append("💨 Промах! (штраф проклятия)")
            return False
        if guaranteed_hit:
            dmg = round(stats["damage"] * random.uniform(0.9, 1.1) * dmg_multiplier)
            is_crit = force_crit or (random.random() * 100 < stats["crit_chance"])
            if is_crit:
                dmg = round(dmg * stats["crit_damage"] / 100)
            missed = False
        else:
            evasion = 0 if target.get("is_boss") else target["evasion"]
            dmg, is_crit, missed = player_attack(
                stats, monster_evasion=evasion + extra_miss_chance, force_crit=force_crit
            )
            dmg = round(dmg * dmg_multiplier)
        if missed:
            log.append("💨 Промах!")
            return False
            
        if target.get("is_boss"):
            target["accumulated_damage"] = target.get("accumulated_damage", 0) + dmg
        else:
            target["hp"] -= dmg
            
        crit_txt = " 💥" if is_crit else ""
        log.append(f"Удар: -{format_number(dmg)}{crit_txt}")
        
        if "vampirism" in specials:
            heal = round(dmg * 25 / 100)
            if heal > 0:
                log.append(f"🩸 +{format_number(heal)} HP")
                do_hit.heal = do_hit.__dict__.get("heal", 0) + heal
                
        if "poison" in specials and random.random() * 100 < 25:
            target["poison_turns"] = 3
            target["poison_dmg"] = max(1, round(stats["damage"] * 0.3))
            log.append("☠️ Отравлен!")
            
        return is_crit

    do_hit.heal = 0

    if target.get("poison_turns", 0) > 0:
        if target.get("is_boss"):
            target["accumulated_damage"] += target["poison_dmg"]
        else:
            target["hp"] -= target["poison_dmg"]
        target["poison_turns"] -= 1
        log.append(f"☠️ Яд: -{format_number(target['poison_dmg'])}")

    puncture_crit = "puncture" in specials and random.random() * 100 < 15
    was_crit = do_hit(force_crit=(force_crit or puncture_crit))

    if (target.get("is_boss") or target.get("hp", 0) > 0) and was_crit and "frenzy" in specials and random.random() * 100 < 30:
        log.append("🌀 Бешенство!")
        do_hit(force_crit=force_crit)

    return do_hit.heal


def _resolve_monster_counter(target, stats, specials, log, evasion_penalty=0, block_percent=0, guaranteed_dodge=False):
    if guaranteed_dodge:
        log.append("💨 Ты уворачиваешься на рывке!")
        return 0
    effective_stats = dict(stats)
    if evasion_penalty:
        effective_stats["evasion"] = max(0.0, stats["evasion"] - evasion_penalty)
        
    if target.get("is_boss"):
        dodged = False
        mdmg = round(stats["max_hp"] * random.uniform(0.18, 0.28))
    else:
        mdmg, dodged = monster_attack(target, effective_stats)
        
    camouflage_triggered = False
    if not dodged and not target.get("is_boss") and "camouflage" in specials and random.random() * 100 < 20:
        dodged, mdmg, camouflage_triggered = True, 0, True
        
    if not dodged and block_percent:
        blocked = round(mdmg * block_percent / 100)
        mdmg -= blocked
        log.append(f"{SHIELD_ABILITY['name']} блокировал {format_number(blocked)} урона!")
        
    if dodged:
        log.append("🌊 Уклонился!" if not camouflage_triggered else "🌊 Маскировка спасла!")
    else:
        log.append(f"Враг бьёт: -{format_number(mdmg)}")
    return mdmg


async def _finish_turn(call, user_id, fsm_data, state: FSMContext, is_camp, target, log):
    message = call.message
    cur_hp = fsm_data["cur_hp"]
    monster = fsm_data["monster"]
    stats = fsm_data["stats"]
    abilities = fsm_data["abilities"]
    specials = fsm_data["specials"]
    original_monster_json = fsm_data["original_monster_json"]
    msg_id = fsm_data.get("battle_message_id", message.message_id)
    
    last_line = "\n".join(log)

    if cur_hp <= 0:
        # Игрок погиб — обращаемся к БД для сохранения и сбрасываем память
        user_db = await database.run_async(database.get_user, user_id)
        if target.get("is_boss"):
            await database.run_async(database.add_event_damage, target["event_id"], user_id, target["accumulated_damage"])
            cooldown_ts = int(time.time()) + int(3.5 * 3600)
            recovered_hp = stats["max_hp"]
            applied = await database.run_async(
                database.try_apply_attack_result,
                user_id, original_monster_json,
                in_hunt=0, monster_json=None, cur_hp=recovered_hp,
                last_hp_regen_ts=int(time.time()), boss_cooldown_ts=cooldown_ts
            )
            if not applied:
                return
            final_text = (
                f"☠️ <b>Босс сокрушил тебя!</b>\n"
                f"Ты нанёс <b>{format_number(target['accumulated_damage'])}</b> урона (сохранено в рейтинге ивента).\n"
                f"Твой панцирь разбит, нужно 3.5 часа на восстановление.\n\n" + last_line
            )
            await state.set_data({})
            await _push_battle_update(message, user_id, msg_id, final_text)
            await message.answer("Обычная охота всё ещё доступна.", reply_markup=hunt_kb(False))
            return
        else:
            knock_to = defeat_knockback_meters(user_db["cur_meters"])
            recovered_hp = stats["max_hp"]
            applied = await database.run_async(
                database.try_apply_attack_result,
                user_id, original_monster_json,
                in_hunt=0, monster_json=None, cur_hp=recovered_hp,
                cur_meters=knock_to, last_hp_regen_ts=int(time.time()),
            )
            if not applied:
                return
            final_text = (
                f"💔 <b>Панцирь треснул!</b> Тебя отбросило назад до {format_number(knock_to)} м.\n"
                f"Прочность восстановлена полностью — можешь пробовать снова прямо сейчас.\n\n" + last_line
            )
            await state.set_data({})
            await _push_battle_update(message, user_id, msg_id, final_text)
            await message.answer("Можешь продолжать рыскать по дну.", reply_markup=hunt_kb(False))
            return

    if not target.get("is_boss") and target.get("hp", 1) <= 0:
        bonus_guard_index = None
        if abilities.get("mark_active"):
            abilities["mark_bonus_earned"] = True
            abilities["mark_active"] = False
            if is_camp:
                abilities["mark_bonus_guard_index"] = monster["current"]
        if is_camp:
            bonus_guard_index = abilities.get("mark_bonus_guard_index")
        gold_extra_mult = MARK_ABILITY["gold_mult"] if abilities.get("mark_bonus_earned") else 1.0

        resource = roll_kill_resource()
        user_db = await database.run_async(database.get_user, user_id)
        
        if is_camp:
            monster["defeated"][monster["current"]] = True
            remaining = [i for i, d in enumerate(monster["defeated"]) if not d]
            if remaining:
                monster["current"] = remaining[0]
                text, ikb = _render_camp(
                    cur_hp, stats["max_hp"], monster, fsm_data["crab_type"],
                    last_line=last_line + "\n\n🎯 Выбери следующую цель.",
                )
                await state.update_data(monster=monster, cur_hp=cur_hp, abilities=abilities)
                await _push_battle_update(message, user_id, msg_id, text, ikb)
                return
            
            total_gold = sum(
                round(gold_reward(g, stats, user_db) * (gold_extra_mult if i == bonus_guard_index else 1.0))
                for i, g in enumerate(monster["guards"])
            )
            
            if "greed" in specials and random.random() * 100 < 20:
                total_gold *= 2
                log.append("🪙 Жадный панцирь удвоил золото!")
                
            last_line = "\n".join(log)
            new_max_meters = max(user_db["max_meters"], monster["meters"])
            
            applied = await database.run_async(
                database.try_apply_attack_result,
                user_id, original_monster_json,
                in_hunt=0, monster_json=None, cur_hp=cur_hp,
                gold=user_db["gold"] + total_gold, kills=user_db["kills"] + 3,
                cur_meters=monster["meters"], max_meters=new_max_meters,
                total_earned_gold=user_db["total_earned_gold"] + total_gold,
                last_hp_regen_ts=int(time.time()),
            )
            if not applied:
                return
            if resource:
                await database.run_async(database.add_resource, user_id, resource)
            
            bonus_txt = " (учтён бонус 🪝 Проклятия на одного из стражей)" if bonus_guard_index is not None else ""
            final_text = "🏆 <b>Засада зачищена!</b>\n" + last_line + f"\n\n💰 Получено золота за всех троих: {format_number(total_gold)}{bonus_txt}"
            await state.set_data({})
            await _push_battle_update(message, user_id, msg_id, final_text)
            await message.answer("Готов к новому рысканью по дну.", reply_markup=hunt_kb(False))
            return

        gold = round(gold_reward(monster, stats, user_db) * gold_extra_mult)
        if "greed" in specials and random.random() * 100 < 20:
            gold *= 2
            log.append("🪙 Жадный панцирь удвоил золото!")
            
        last_line = "\n".join(log)
        new_max_meters = max(user_db["max_meters"], monster["meters"])
        applied = await database.run_async(
            database.try_apply_attack_result,
            user_id, original_monster_json,
            in_hunt=0, monster_json=None, cur_hp=cur_hp,
            gold=user_db["gold"] + gold, kills=user_db["kills"] + 1,
            cur_meters=monster["meters"], max_meters=new_max_meters,
            total_earned_gold=user_db["total_earned_gold"] + gold,
            last_hp_regen_ts=int(time.time()),
        )
        if not applied:
            return
        if resource:
            await database.run_async(database.add_resource, user_id, resource)
        
        bonus_txt = " (×2 от 🪝 Проклятия)" if gold_extra_mult != 1.0 else ""
        final_text = "🏆 <b>Победа!</b>\n" + last_line + f"\n\n💰 Золото: {format_number(gold)}{bonus_txt}"
        await state.set_data({})
        await _push_battle_update(message, user_id, msg_id, final_text)
        await message.answer("Готов к новому рысканью по дну.", reply_markup=hunt_kb(False))
        return

    # Бой продолжается — обновляем ТОЛЬКО быструю память
    await state.update_data(monster=monster, cur_hp=cur_hp, abilities=abilities)

    if is_camp:
        text, ikb = _render_camp(cur_hp, stats["max_hp"], monster, fsm_data["crab_type"], last_line=last_line)
    else:
        text, ikb = _render_single(cur_hp, stats["max_hp"], monster, fsm_data["crab_type"], last_line=last_line)

    await _push_battle_update(message, user_id, msg_id, text, ikb)


@router.callback_query(F.data == "hunt_attack")
async def attack(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    ctx = await _load_battle_context(user_id, state)
    if not ctx:
        await call.answer("Сейчас не с кем сражаться. Нажми «🔎 Рыскать по дну».", show_alert=True)
        return
        
    fsm_data, is_camp, target = ctx
    await call.answer()

    stats = fsm_data["stats"]
    specials = fsm_data["specials"]
    abilities = fsm_data["abilities"]
    cur_hp = fsm_data["cur_hp"]
    log = []

    if target.get("is_boss"):
        specials = []

    consumed_sprint = abilities.get("sprint_turns", 0) > 0
    consumed_mark_miss = abilities.get("mark_miss_turns", 0) > 0

    guaranteed_miss = consumed_mark_miss
    guaranteed_hit = consumed_sprint and not guaranteed_miss
    force_crit = abilities.get("rage_active", False)

    heal = _do_combat_round(
        target, stats, specials, log,
        force_crit=force_crit, guaranteed_hit=guaranteed_hit, guaranteed_miss=guaranteed_miss,
        extra_miss_chance=(UNIQUE_ABILITIES[2]["fatigue_miss_bonus"] if abilities.get("fatigue_turns", 0) > 0 else 0),
    )
    cur_hp = min(stats["max_hp"], cur_hp + heal)

    if abilities.get("rage_active", False):
        self_dmg = round(stats["max_hp"] * UNIQUE_ABILITIES[3]["self_damage_percent"] / 100)
        cur_hp -= self_dmg
        log.append(f"🩸 Раж отбирает {format_number(self_dmg)} прочности")

    if consumed_sprint:
        abilities["sprint_turns"] -= 1
        if abilities["sprint_turns"] == 0:
            abilities["fatigue_turns"] = UNIQUE_ABILITIES[2]["fatigue_turns"]
    if consumed_mark_miss:
        abilities["mark_miss_turns"] -= 1
    _tick_ability_timers(abilities, consumed_sprint=consumed_sprint)

    if target.get("is_boss") or target.get("hp", 0) > 0:
        evasion_penalty = UNIQUE_ABILITIES[2]["fatigue_evasion_penalty"] if abilities.get("fatigue_turns", 0) > 0 else 0
        mdmg = _resolve_monster_counter(
            target, stats, specials, log, evasion_penalty=evasion_penalty, guaranteed_dodge=consumed_sprint
        )
        cur_hp -= mdmg
        
    fsm_data["cur_hp"] = cur_hp
    await _finish_turn(call, user_id, fsm_data, state, is_camp, target, log)


@router.callback_query(F.data == "ability_shield")
async def ability_shield(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    ctx = await _load_battle_context(user_id, state)
    if not ctx:
        await call.answer("Сейчас не с кем сражаться.", show_alert=True)
        return
        
    fsm_data, is_camp, target = ctx
    abilities = fsm_data["abilities"]

    if target.get("is_boss"):
        await call.answer("Способности бесполезны против этого существа!", show_alert=True)
        return
    if abilities["shield_cooldown"] > 0:
        await call.answer(f"Щит перезаряжается ещё {abilities['shield_cooldown']} х.", show_alert=True)
        return
    await call.answer()

    stats = fsm_data["stats"]
    specials = fsm_data["specials"]
    cur_hp = fsm_data["cur_hp"]
    log = [f"{SHIELD_ABILITY['name']} поднят!"]

    if target.get("poison_turns", 0) > 0:
        target["hp"] -= target["poison_dmg"]
        target["poison_turns"] -= 1
        log.append(f"☠️ Яд: -{format_number(target['poison_dmg'])}")

    _tick_ability_timers(abilities)
    abilities["shield_cooldown"] = SHIELD_ABILITY["cooldown_turns"]

    if target["hp"] > 0:
        mdmg = _resolve_monster_counter(target, stats, specials, log, block_percent=SHIELD_ABILITY["block_percent"])
        cur_hp -= mdmg

    fsm_data["cur_hp"] = cur_hp
    await _finish_turn(call, user_id, fsm_data, state, is_camp, target, log)


@router.callback_query(F.data == "ability_mark")
async def ability_mark(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    ctx = await _load_battle_context(user_id, state)
    if not ctx:
        await call.answer("Сейчас не с кем сражаться.", show_alert=True)
        return
        
    fsm_data, is_camp, target = ctx
    abilities = fsm_data["abilities"]

    if target.get("is_boss"):
        await call.answer("Способности бесполезны против этого существа!", show_alert=True)
        return
    if abilities["mark_used"]:
        await call.answer("Проклятие уже использовано в этом бою.", show_alert=True)
        return
    await call.answer()

    stats = fsm_data["stats"]
    specials = fsm_data["specials"]
    cur_hp = fsm_data["cur_hp"]
    log = ["🪝 Проклятие золотого краба! Следующие 2 удара промахнутся, но добивание даст ×2 золота."]

    if target.get("poison_turns", 0) > 0:
        target["hp"] -= target["poison_dmg"]
        target["poison_turns"] -= 1
        log.append(f"☠️ Яд: -{format_number(target['poison_dmg'])}")

    abilities["mark_used"] = True
    abilities["mark_active"] = True
    abilities["mark_miss_turns"] = MARK_ABILITY["miss_turns"]
    _tick_ability_timers(abilities)

    if target["hp"] > 0:
        mdmg = _resolve_monster_counter(target, stats, specials, log)
        cur_hp -= mdmg

    fsm_data["cur_hp"] = cur_hp
    await _finish_turn(call, user_id, fsm_data, state, is_camp, target, log)


@router.callback_query(F.data == "ability_unique")
async def ability_unique(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    ctx = await _load_battle_context(user_id, state)
    if not ctx:
        await call.answer("Сейчас не с кем сражаться.", show_alert=True)
        return
        
    fsm_data, is_camp, target = ctx
    abilities = fsm_data["abilities"]

    if target.get("is_boss"):
        await call.answer("Способности бесполезны против этого существа!", show_alert=True)
        return
    if abilities["unique_used"]:
        await call.answer("Уникальная способность уже использована в этом бою.", show_alert=True)
        return
    await call.answer()

    stats = fsm_data["stats"]
    specials = fsm_data["specials"]
    cur_hp = fsm_data["cur_hp"]
    crab_type = fsm_data["crab_type"]
    
    ability = UNIQUE_ABILITIES.get(crab_type, UNIQUE_ABILITIES[1])
    abilities["unique_used"] = True
    log = [f"{ability['name']}!"]

    consumed_mark_miss = abilities.get("mark_miss_turns", 0) > 0

    if crab_type == 1:
        heal = _do_combat_round(target, stats, specials, log, dmg_multiplier=ability["damage_mult"], guaranteed_miss=consumed_mark_miss)
        cur_hp = min(stats["max_hp"], cur_hp + heal)
        self_dmg = round(stats["max_hp"] * ability["self_damage_percent"] / 100)
        cur_hp -= self_dmg
        log.append(f"💥 Отдача: -{format_number(self_dmg)} прочности")
        if consumed_mark_miss:
            abilities["mark_miss_turns"] -= 1
        _tick_ability_timers(abilities)
        if target["hp"] > 0 and cur_hp > 0:
            mdmg = _resolve_monster_counter(target, stats, specials, log)
            cur_hp -= mdmg

    elif crab_type == 2:
        abilities["sprint_turns"] = ability["sprint_turns"]
        log.append("💨 Ты срываешься с места — враг не успевает ответить!")
        _tick_ability_timers(abilities)

    elif crab_type == 3:
        abilities["rage_active"] = True
        heal = _do_combat_round(target, stats, specials, log, force_crit=True, guaranteed_miss=consumed_mark_miss)
        cur_hp = min(stats["max_hp"], cur_hp + heal)
        self_dmg = round(stats["max_hp"] * ability["self_damage_percent"] / 100)
        cur_hp -= self_dmg
        log.append(f"🩸 Раж отбирает {format_number(self_dmg)} прочности")
        if consumed_mark_miss:
            abilities["mark_miss_turns"] -= 1
        _tick_ability_timers(abilities)
        if target["hp"] > 0 and cur_hp > 0:
            mdmg = _resolve_monster_counter(target, stats, specials, log)
            cur_hp -= mdmg
    else:
        _tick_ability_timers(abilities)

    fsm_data["cur_hp"] = cur_hp
    await _finish_turn(call, user_id, fsm_data, state, is_camp, target, log)


@router.message(Nav.hunt, F.text == "↩️ Бочком назад")
async def retreat(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await database.run_async(database.get_user, user_id)
    
    if user["in_hunt"]:
        # Сбрасываем флаг битвы в БД одним запросом
        await database.run_async(
            database.update_user,
            user_id, in_hunt=0, monster_json=None,
            last_hp_regen_ts=int(time.time()),
        )
        # Очищаем быструю память
        await state.set_data({})
        
        if user["battle_message_id"]:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id, message_id=user["battle_message_id"],
                    text="↩️ Ты ушёл боком, сохранив позицию и прочность. Награды не будет.",
                )
            except Exception:
                pass
                
    await message.answer(
        "Позиция и прочность сохранены как есть, награды не будет. Прочность восстановится сама со временем.",
        reply_markup=hunt_kb(False),
    )
