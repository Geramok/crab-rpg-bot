# -*- coding: utf-8 -*-
import html
import random
import time

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import SHIELD_ABILITY, UNIQUE_ABILITIES, NECTARS_DATA
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

def _tick_ability_timers(abilities, consumed_sprint=False):
    if abilities["shield_cooldown"] > 0:
        abilities["shield_cooldown"] -= 1
    if abilities["fatigue_turns"] > 0 and not consumed_sprint:
        abilities["fatigue_turns"] -= 1

def _hp_bar(current, total, length=10):
    current = max(0, current)
    total = max(1, total)
    filled = max(0, min(length, round(length * current / total)))
    return "█" * filled + "░" * (length - filled)

def _abilities_status_line(abilities, crab_type, nectars):
    parts = []
    if abilities["sprint_turns"] > 0:
        parts.append(f"💨 Рывок: ещё {abilities['sprint_turns']} х.")
    if abilities["fatigue_turns"] > 0:
        parts.append(f"😮‍💨 Устал: ещё {abilities['fatigue_turns']} х.")
    if abilities["rage_active"]:
        parts.append("🩸 Раж активен")
        
    # Отображение пассивных нектаров
    if nectars.get("strength_charges", 0) > 0:
        parts.append(f"🔴 Сила (боёв: {nectars['strength_charges']})")
    if nectars.get("combat_effects", {}).get("rage"):
        parts.append("🟠 ЯРОСТЬ Джоджо!")
    if nectars.get("combat_effects", {}).get("sparkling"):
        parts.append("🟢 Золотая лихорадка")
        
    return " | ".join(parts)

def _abilities_buttons(abilities, crab_type, nectars):
    shield_name = SHIELD_ABILITY["name"]
    shield_label = shield_name if abilities["shield_cooldown"] <= 0 else f"{shield_name} ({abilities['shield_cooldown']})"
    
    unique = UNIQUE_ABILITIES.get(crab_type, UNIQUE_ABILITIES[1])
    unique_label = unique["name"] if not abilities["unique_used"] else f"{unique['name']} (исп.)"
    
    buttons = [[InlineKeyboardButton(text=shield_label, callback_data="ability_shield")]]
    
    # Кнопка надетого нектара
    active_nectar = nectars.get("active_nectar")
    inv = nectars.get("nectars_inv", {})
    if active_nectar and inv.get(active_nectar, 0) > 0:
        nectar_name = NECTARS_DATA[active_nectar]["name"]
        buttons[0].append(InlineKeyboardButton(text=f"🫙 Выпить {nectar_name}", callback_data=f"drink_nectar"))
        
    buttons.append([InlineKeyboardButton(text=unique_label, callback_data="ability_unique")])
    return buttons

def _render_single(user_cur_hp, stats_max_hp, monster, crab_type, nectars, last_line=None):
    meters = monster.get("meters", "???")
    
    if monster.get("is_boss"):
        text = (
            f"<pre>{html.escape(monster['art'])}</pre>\n"
            f"🐉 <b>{monster['name']}</b>\n"
            f"🌊 Глубина: <b>{format_number(meters)} м</b>\n"
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
        f"🌊 Глубина: <b>{format_number(meters)} м</b>\n"
        f"❤️ Враг:  [{_hp_bar(monster['hp'], monster['max_hp'])}] {format_number(max(monster['hp'], 0))}/{format_number(monster['max_hp'])}\n"
        f"🦀 Ты:    [{_hp_bar(user_cur_hp, stats_max_hp)}] {format_number(max(user_cur_hp, 0))}/{format_number(stats_max_hp)}\n"
    )
    status = _abilities_status_line(abilities, crab_type, nectars)
    if status:
        text += f"{status}\n"
    if last_line:
        text += f"\n{last_line}"
    buttons = [[ATTACK_BUTTON]] + _abilities_buttons(abilities, crab_type, nectars)
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)

def _render_camp(user_cur_hp, stats_max_hp, camp, crab_type, nectars, last_line=None):
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
    ab_status = _abilities_status_line(abilities, crab_type, nectars)
    if ab_status:
        text += f"{ab_status}\n"
    if last_line:
        text += f"\n{last_line}"
    buttons.append([ATTACK_BUTTON])
    buttons += _abilities_buttons(abilities, crab_type, nectars)
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)

async def _push_battle_update(message, user_id, message_id, text, reply_markup=None):
    try:
        await message.bot.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=text, reply_markup=reply_markup)
        return message_id
    except TelegramBadRequest:
        sent = await message.answer(text, reply_markup=reply_markup)
        return sent.message_id

async def perform_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    if "monster" in data:
        await message.answer("⚔️ Ты уже в бою!", reply_markup=hunt_kb(True))
        return
        
    user = await database.run_async(database.get_user, user_id)
    nectars_db = await database.get_nectars_data(user_id)
    nectars_db["combat_effects"] = {} # Эффекты текущего боя
    
    redis_client = state.storage.redis
    buffered_meters = await redis_client.hget(f"user_buffer:{user_id}", "cur_meters")
    buffered_hp = await redis_client.hget(f"user_buffer:{user_id}", "cur_hp")
    if buffered_meters: user["cur_meters"] = int(buffered_meters)
    if buffered_hp is not None: user["cur_hp"] = float(buffered_hp)

    stones = await database.run_async(database.get_stones, user_id)
    mutations = await database.run_async(database.get_mutations_v2, user_id)
    stats = get_effective_stats(user, stones, mutations)
    healed_hp = apply_idle_regen(user, stats, int(time.time()))
    crab_type = user["crab_type"]

    new_meters = next_monster_meters(user["cur_meters"], mutations)
    barrier = get_blocking_barrier(new_meters, mutations)
    barrier_line = None
    if barrier:
        barrier_meters, required = barrier
        have = total_mutation_levels(mutations)
        barrier_line = f"🚧 <b>Стена прокачки на {format_number(barrier_meters)}м!</b> Нужно {required} уровней мутаций (сейчас {have})."

    is_elite = is_elite_encounter_meter(user["cur_meters"], new_meters)
    monster = roll_monster(new_meters, elite_mult=ELITE_ENCOUNTER_MULT if is_elite else 1.0)
    monster["meters"] = new_meters
    monster["elite"] = is_elite
    
    text, ikb = _render_single(healed_hp, stats["max_hp"], monster, crab_type, nectars_db)
    if barrier_line: text = f"{barrier_line}\n\n{text}"

    await message.answer("🫧 Вглядываемся в муть...", reply_markup=hunt_kb(True))
    sent = await message.answer(text, reply_markup=ikb)
    
    await state.update_data(
        cur_hp=healed_hp, stats=stats, specials=list(get_equipped_special_effects(mutations)),
        crab_type=crab_type, cur_meters=user["cur_meters"], max_meters=user["max_meters"],
        monster=monster, abilities=_get_abilities(monster), battle_message_id=sent.message_id, nectars=nectars_db
    )

@router.message(StateFilter(Nav.hunt, Nav.main, None), F.text.contains("Рыскать по дну"))
async def search_enemy(message: Message, state: FSMContext):
    await state.set_state(Nav.hunt)
    await perform_search(message, state)

async def _load_battle_context(user_id, state: FSMContext):
    data = await state.get_data()
    if "monster" not in data: return None
    is_camp = data["monster"].get("is_camp", False)
    target = data["monster"]["guards"][data["monster"]["current"]] if is_camp else data["monster"]
    return data, is_camp, target

@router.callback_query(F.data.startswith("pick_guard_"))
async def pick_guard(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split("_")[-1])
    ctx = await _load_battle_context(call.from_user.id, state)
    if not ctx: return
    data, is_camp, target = ctx
    camp = data["monster"]
    if not camp.get("is_camp") or camp["defeated"][idx]: return
    camp["current"] = idx
    await state.update_data(monster=camp)
    text, ikb = _render_camp(data["cur_hp"], data["stats"]["max_hp"], camp, data["crab_type"], data["nectars"])
    try: await call.answer()
    except TelegramBadRequest: pass
    await _push_battle_update(call.message, call.from_user.id, data.get("battle_message_id", call.message.message_id), text, ikb)

def _do_combat_round(target, stats, specials, log, force_crit=False, guaranteed_hit=False, dmg_multiplier=1.0, extra_miss_chance=0, nectars=None):
    nectar_eff = nectars.get("combat_effects", {}) if nectars else {}
    if nectars and nectars.get("strength_charges", 0) > 0:
        dmg_multiplier *= 1.20
    if nectar_eff.get("rage"):
        dmg_multiplier *= 0.50
        guaranteed_hit = True

    def do_hit(force_crit=force_crit):
        if guaranteed_hit:
            dmg = round(stats["damage"] * random.uniform(0.9, 1.1) * dmg_multiplier)
            is_crit = force_crit or (random.random() * 100 < stats["crit_chance"])
            if is_crit: dmg = round(dmg * stats["crit_damage"] / 100)
            missed = False
        else:
            evasion = 0 if target.get("is_boss") else target["evasion"]
            dmg, is_crit, missed = player_attack(stats, monster_evasion=evasion + extra_miss_chance, force_crit=force_crit)
            dmg = round(dmg * dmg_multiplier)
            
        if missed:
            log.append("💨 Промах!")
            return False
            
        if target.get("is_boss"): target["accumulated_damage"] = target.get("accumulated_damage", 0) + dmg
        else: target["hp"] -= dmg
            
        crit_txt = " 💥" if is_crit else ""
        if nectar_eff.get("rage"): crit_txt += " (ORA-ORA!)"
        log.append(f"Удар: -{format_number(dmg)}{crit_txt}")
        
        if "vampirism" in specials:
            heal = min(round(dmg * 0.25), round(stats["max_hp"] * 0.10))
            if heal > 0:
                log.append(f"🩸 +{format_number(heal)} HP")
                do_hit.heal = do_hit.__dict__.get("heal", 0) + heal
                
        if "poison" in specials and random.random() * 100 < 15:
            target["poison_turns"] = 3
            target["poison_dmg"] = max(1, round(stats["damage"] * 0.3))
            log.append("☠️ Отравлен!")
        return is_crit

    do_hit.heal = 0
    if target.get("poison_turns", 0) > 0:
        if target.get("is_boss"): target["accumulated_damage"] += target["poison_dmg"]
        else: target["hp"] -= target["poison_dmg"]
        target["poison_turns"] -= 1
        log.append(f"☠️ Яд: -{format_number(target['poison_dmg'])}")

    was_crit = do_hit(force_crit=(force_crit or ("puncture" in specials and random.random() * 100 < 10)))
    if (target.get("is_boss") or target.get("hp", 0) > 0) and was_crit and "frenzy" in specials and random.random() * 100 < 20:
        log.append("🌀 Бешенство!")
        do_hit(force_crit=force_crit)
    return do_hit.heal

def _resolve_monster_counter(target, stats, specials, log, evasion_penalty=0, block_percent=0, guaranteed_dodge=False, nectars=None):
    if guaranteed_dodge:
        log.append("💨 Ты уворачиваешься на рывке!")
        return 0
        
    effective_stats = dict(stats)
    nectar_eff = nectars.get("combat_effects", {}) if nectars else {}
    if nectar_eff.get("rage"):
        effective_stats["evasion"] = min(100.0, stats["evasion"] + 50.0)

    if evasion_penalty:
        effective_stats["evasion"] = max(0.0, effective_stats["evasion"] - evasion_penalty)
        
    if target.get("is_boss"):
        dodged, mdmg = False, round(stats["max_hp"] * random.uniform(0.18, 0.28))
    else:
        mdmg, dodged = monster_attack(target, effective_stats)
        
    camouflage_triggered = False
    if not dodged and not target.get("is_boss") and "camouflage" in specials and random.random() * 100 < 10:
        dodged, mdmg, camouflage_triggered = True, 0, True
        
    if not dodged and block_percent:
        blocked = round(mdmg * block_percent / 100)
        mdmg -= blocked
        log.append(f"{SHIELD_ABILITY['name']} блокировал {format_number(blocked)} урона!")
        
    if dodged:
        txt = "🌊 Уклонился!" if not camouflage_triggered else "🌊 Маскировка спасла!"
        if nectar_eff.get("rage"): txt = "💨 Идеальное Джоджо-уклонение!"
        log.append(txt)
    else:
        log.append(f"Враг бьёт: -{format_number(mdmg)}")
    return mdmg

async def _finish_turn(call, user_id, fsm_data, state: FSMContext, is_camp, target, log):
    message, cur_hp, stats, abilities = call.message, fsm_data["cur_hp"], fsm_data["stats"], fsm_data["abilities"]
    nectars = fsm_data["nectars"]
    msg_id = fsm_data.get("battle_message_id", message.message_id)
    last_line, now = "\n".join(log), int(time.time())
    redis_client = state.storage.redis

    # 1. Краб погиб
    if cur_hp <= 0:
        await database.flush_user_buffer(redis_client, user_id)
        user_db = await database.run_async(database.get_user, user_id)
        
        if target.get("is_boss"):
            await database.run_async(database.add_event_damage, target["event_id"], user_id, target["accumulated_damage"])
            await database.run_async(database.update_user, user_id, cur_hp=stats["max_hp"], last_hp_regen_ts=now, boss_cooldown_ts=now + int(3.5 * 3600))
            await state.set_data({})
            await _push_battle_update(message, user_id, msg_id, f"☠️ <b>Босс сокрушил тебя!</b>\nНанесено <b>{format_number(target['accumulated_damage'])}</b> урона.\nПанцирь разбит, нужно 3.5 часа.\n\n{last_line}")
            await message.answer("Обычная охота доступна.", reply_markup=hunt_kb(False))
            return
        else:
            knock = defeat_knockback_meters(user_db["cur_meters"])
            await database.run_async(database.update_user, user_id, cur_hp=stats["max_hp"], cur_meters=knock, last_hp_regen_ts=now)
            await state.set_data({})
            await _push_battle_update(message, user_id, msg_id, f"💔 <b>Панцирь треснул!</b> Отбросило до {format_number(knock)} м.\n\n{last_line}")
            await message.answer("Можешь продолжать рыскать.", reply_markup=hunt_kb(False))
            return

    # 2. Враг побежден
    if not target.get("is_boss") and target.get("hp", 1) <= 0:
        user_db = await database.run_async(database.get_user, user_id)
        nectar_eff = nectars.get("combat_effects", {})
        
        # Засада
        if is_camp:
            monster = fsm_data["monster"]
            monster["defeated"][monster["current"]] = True
            remaining = [i for i, d in enumerate(monster["defeated"]) if not d]
            if remaining:
                monster["current"] = remaining[0]
                text, ikb = _render_camp(cur_hp, stats["max_hp"], monster, fsm_data["crab_type"], nectars, last_line=last_line + "\n\n🎯 Следующая цель.")
                await state.update_data(monster=monster, cur_hp=cur_hp, abilities=abilities)
                await _push_battle_update(message, user_id, msg_id, text, ikb)
                return
            
            mult = 2.5 if nectar_eff.get("sparkling") else 1.0
            total_gold = sum(round(gold_reward(g, stats, user_db) * mult) for g in monster["guards"])
            if "greed" in fsm_data["specials"] and random.random() * 100 < 15:
                total_gold *= 2
                log.append("🪙 Жадный панцирь удвоил золото!")
                
            await database.add_to_buffer(redis_client, user_id, gold=total_gold, kills=3, cur_meters=monster["meters"], max_meters=max(user_db["max_meters"], monster["meters"]), cur_hp=cur_hp, last_hp_regen_ts=now)
            
            if nectars["strength_charges"] > 0:
                nectars["strength_charges"] -= 1
                await database.update_nectars_data(user_id, strength_charges=nectars["strength_charges"])
                
            await state.set_data({})
            await _push_battle_update(message, user_id, msg_id, f"🏆 <b>Засада зачищена!</b>\n{chr(10).join(log)}\n\n💰 Получено золота: {format_number(total_gold)}")
            await message.answer("Готов к новому рысканью.", reply_markup=hunt_kb(False))
            return

        # Обычный монстр
        mult = 2.5 if nectar_eff.get("sparkling") else 1.0
        gold = round(gold_reward(fsm_data["monster"], stats, user_db) * mult)
        if "greed" in fsm_data["specials"] and random.random() * 100 < 15:
            gold *= 2
            log.append("🪙 Жадный панцирь удвоил золото!")
            
        await database.add_to_buffer(redis_client, user_id, gold=gold, kills=1, cur_meters=fsm_data["monster"]["meters"], max_meters=max(user_db["max_meters"], fsm_data["monster"]["meters"]), cur_hp=cur_hp, last_hp_regen_ts=now)
        
        if nectars["strength_charges"] > 0:
            nectars["strength_charges"] -= 1
            await database.update_nectars_data(user_id, strength_charges=nectars["strength_charges"])
            
        await state.set_data({})
        await _push_battle_update(message, user_id, msg_id, f"🏆 <b>Победа!</b>\n{chr(10).join(log)}\n\n💰 Золото: {format_number(gold)}")
        await message.answer("Готов к новому рысканью.", reply_markup=hunt_kb(False))
        return

    # 3. Бой продолжается
    await state.update_data(monster=fsm_data["monster"], cur_hp=cur_hp, abilities=abilities, nectars=nectars)
    if is_camp: text, ikb = _render_camp(cur_hp, stats["max_hp"], fsm_data["monster"], fsm_data["crab_type"], nectars, last_line)
    else: text, ikb = _render_single(cur_hp, stats["max_hp"], fsm_data["monster"], fsm_data["crab_type"], nectars, last_line)
    await _push_battle_update(message, user_id, msg_id, text, ikb)

@router.callback_query(F.data == "hunt_attack")
async def attack(call: CallbackQuery, state: FSMContext):
    ctx = await _load_battle_context(call.from_user.id, state)
    if not ctx:
        try: await call.answer("Сейчас не с кем сражаться.", show_alert=True)
        except TelegramBadRequest: pass
        return
    fsm_data, is_camp, target = ctx
    try: await call.answer()
    except TelegramBadRequest: pass

    log, abilities, cur_hp = [], fsm_data["abilities"], fsm_data["cur_hp"]
    consumed_sprint = abilities.get("sprint_turns", 0) > 0

    heal = _do_combat_round(
        target, fsm_data["stats"], [] if target.get("is_boss") else fsm_data["specials"], log,
        force_crit=abilities.get("rage_active", False), guaranteed_hit=consumed_sprint,
        extra_miss_chance=(UNIQUE_ABILITIES[2]["fatigue_miss_bonus"] if abilities.get("fatigue_turns", 0) > 0 else 0),
        nectars=fsm_data["nectars"]
    )
    cur_hp = min(fsm_data["stats"]["max_hp"], cur_hp + heal)

    if abilities.get("rage_active", False):
        self_dmg = round(fsm_data["stats"]["max_hp"] * UNIQUE_ABILITIES[3]["self_damage_percent"] / 100)
        cur_hp -= self_dmg
        log.append(f"🩸 Раж отбирает {format_number(self_dmg)} прочности")

    if consumed_sprint:
        abilities["sprint_turns"] -= 1
        if abilities["sprint_turns"] == 0: abilities["fatigue_turns"] = UNIQUE_ABILITIES[2]["fatigue_turns"]
    _tick_ability_timers(abilities, consumed_sprint=consumed_sprint)

    if target.get("is_boss") or target.get("hp", 0) > 0:
        evasion_penalty = UNIQUE_ABILITIES[2]["fatigue_evasion_penalty"] if abilities.get("fatigue_turns", 0) > 0 else 0
        cur_hp -= _resolve_monster_counter(target, fsm_data["stats"], fsm_data["specials"], log, evasion_penalty=evasion_penalty, guaranteed_dodge=consumed_sprint, nectars=fsm_data["nectars"])
        
    fsm_data["cur_hp"] = cur_hp
    await _finish_turn(call, call.from_user.id, fsm_data, state, is_camp, target, log)

@router.callback_query(F.data == "drink_nectar")
async def drink_nectar(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    ctx = await _load_battle_context(user_id, state)
    if not ctx:
        try: await call.answer("Не в бою!", show_alert=True)
        except TelegramBadRequest: pass
        return
    fsm_data, is_camp, target = ctx
    nectars = fsm_data["nectars"]
    active = nectars["active_nectar"]
    inv = nectars["nectars_inv"]
    
    if not active or inv.get(active, 0) <= 0:
        try: await call.answer("Нет нектара!", show_alert=True)
        except TelegramBadRequest: pass
        return
        
    if active == "strength" and nectars["strength_charges"] > 0:
        try: await call.answer("Сила уже действует!", show_alert=True)
        except TelegramBadRequest: pass
        return

    try: await call.answer()
    except TelegramBadRequest: pass

    # Списываем нектар
    inv[active] -= 1
    await database.update_nectars_data(user_id, nectars_inv=inv)
    
    log = []
    # Эффекты зелья
    if active == "strength":
        nectars["strength_charges"] = 5
        await database.update_nectars_data(user_id, strength_charges=5)
        log.append("🍯 Ты выпил Нектар Силы! Урон увеличен на 5 боев.")
    elif active == "refreshing":
        heal = round(fsm_data["stats"]["max_hp"] * 0.35)
        fsm_data["cur_hp"] = min(fsm_data["stats"]["max_hp"], fsm_data["cur_hp"] + heal)
        log.append(f"🍯 Освежающий нектар восстановил {format_number(heal)} HP!")
    elif active == "rage":
        sacrifice = round(fsm_data["stats"]["max_hp"] * 0.15)
        fsm_data["cur_hp"] -= sacrifice
        nectars["combat_effects"]["rage"] = True
        log.append(f"🍯 Нектар Ярости сжег {format_number(sacrifice)} HP! ORA-ORA-ORA!")
    elif active == "sparkling":
        nectars["combat_effects"]["sparkling"] = True
        log.append("🍯 Сверкающий нектар выпит. Золотая лихорадка началась!")

    # Монстр бьет в ответ (выпивание тратит ход)
    if target.get("is_boss") or target.get("hp", 0) > 0:
        if fsm_data["cur_hp"] > 0: # Если мы не убили себя нектаром ярости
            evasion_penalty = UNIQUE_ABILITIES[2]["fatigue_evasion_penalty"] if fsm_data["abilities"].get("fatigue_turns", 0) > 0 else 0
            fsm_data["cur_hp"] -= _resolve_monster_counter(target, fsm_data["stats"], fsm_data["specials"], log, evasion_penalty=evasion_penalty, nectars=nectars)

    await _finish_turn(call, user_id, fsm_data, state, is_camp, target, log)

@router.callback_query(F.data == "ability_shield")
async def ability_shield(call: CallbackQuery, state: FSMContext):
    # Код щита (остается стандартным)
    ctx = await _load_battle_context(call.from_user.id, state)
    if not ctx: return
    fsm_data, is_camp, target = ctx
    if target.get("is_boss") or fsm_data["abilities"]["shield_cooldown"] > 0:
        try: await call.answer("Недоступно!", show_alert=True)
        except TelegramBadRequest: pass
        return
    try: await call.answer()
    except TelegramBadRequest: pass
    log = [f"{SHIELD_ABILITY['name']} поднят!"]
    _tick_ability_timers(fsm_data["abilities"])
    fsm_data["abilities"]["shield_cooldown"] = SHIELD_ABILITY["cooldown_turns"]
    if target["hp"] > 0:
        fsm_data["cur_hp"] -= _resolve_monster_counter(target, fsm_data["stats"], fsm_data["specials"], log, block_percent=SHIELD_ABILITY["block_percent"], nectars=fsm_data["nectars"])
    await _finish_turn(call, call.from_user.id, fsm_data, state, is_camp, target, log)

@router.callback_query(F.data == "ability_unique")
async def ability_unique(call: CallbackQuery, state: FSMContext):
    # Уникальные способности крабов
    ctx = await _load_battle_context(call.from_user.id, state)
    if not ctx: return
    fsm_data, is_camp, target = ctx
    if target.get("is_boss") or fsm_data["abilities"]["unique_used"]:
        try: await call.answer("Недоступно!", show_alert=True)
        except TelegramBadRequest: pass
        return
    try: await call.answer()
    except TelegramBadRequest: pass

    crab_type = fsm_data["crab_type"]
    ability = UNIQUE_ABILITIES.get(crab_type, UNIQUE_ABILITIES[1])
    fsm_data["abilities"]["unique_used"] = True
    log = [f"{ability['name']}!"]

    if crab_type == 1:
        heal = _do_combat_round(target, fsm_data["stats"], fsm_data["specials"], log, dmg_multiplier=ability["damage_mult"], nectars=fsm_data["nectars"])
        fsm_data["cur_hp"] = min(fsm_data["stats"]["max_hp"], fsm_data["cur_hp"] + heal)
        self_dmg = round(fsm_data["stats"]["max_hp"] * ability["self_damage_percent"] / 100)
        fsm_data["cur_hp"] -= self_dmg
        log.append(f"💥 Отдача: -{format_number(self_dmg)} прочности")
        _tick_ability_timers(fsm_data["abilities"])
        if target["hp"] > 0 and fsm_data["cur_hp"] > 0:
            fsm_data["cur_hp"] -= _resolve_monster_counter(target, fsm_data["stats"], fsm_data["specials"], log, nectars=fsm_data["nectars"])
    elif crab_type == 2:
        fsm_data["abilities"]["sprint_turns"] = ability["sprint_turns"]
        log.append("💨 Ты срываешься с места — враг не успевает ответить!")
        _tick_ability_timers(fsm_data["abilities"])
    elif crab_type == 3:
        fsm_data["abilities"]["rage_active"] = True
        heal = _do_combat_round(target, fsm_data["stats"], fsm_data["specials"], log, force_crit=True, nectars=fsm_data["nectars"])
        fsm_data["cur_hp"] = min(fsm_data["stats"]["max_hp"], fsm_data["cur_hp"] + heal)
        self_dmg = round(fsm_data["stats"]["max_hp"] * ability["self_damage_percent"] / 100)
        fsm_data["cur_hp"] -= self_dmg
        log.append(f"🩸 Раж отбирает {format_number(self_dmg)} прочности")
        _tick_ability_timers(fsm_data["abilities"])
        if target["hp"] > 0 and fsm_data["cur_hp"] > 0:
            fsm_data["cur_hp"] -= _resolve_monster_counter(target, fsm_data["stats"], fsm_data["specials"], log, nectars=fsm_data["nectars"])
    
    await _finish_turn(call, call.from_user.id, fsm_data, state, is_camp, target, log)

@router.message(Nav.hunt, F.text == "↩️ Бочком назад")
async def retreat(message: Message, state: FSMContext):
    data = await state.get_data()
    msg_id, cur_hp, monster = data.get("battle_message_id"), data.get("cur_hp"), data.get("monster")
    user_id = message.from_user.id
    
    if monster and monster.get("is_boss") and monster.get("accumulated_damage", 0) > 0:
        await database.run_async(database.add_event_damage, monster["event_id"], user_id, monster["accumulated_damage"])
    if cur_hp is not None:
        await database.add_to_buffer(state.storage.redis, user_id, cur_hp=cur_hp, last_hp_regen_ts=int(time.time()))
    
    await database.flush_user_buffer(state.storage.redis, user_id)
    await state.set_data({})
    if msg_id:
        try: await message.bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text="↩️ Ты ушёл боком.")
        except Exception: pass
    await message.answer("Позиция сохранена.", reply_markup=hunt_kb(False))
