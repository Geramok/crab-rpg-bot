# -*- coding: utf-8 -*-
import json
import random
import time

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import SPECIAL_MUTATIONS, SHIELD_ABILITY, MARK_ABILITY, UNIQUE_ABILITIES
from game_logic import (
    get_effective_stats, next_monster_meters, roll_monster, is_guard_camp_meter,
    roll_guard_camp, player_attack, monster_attack, gold_reward, apply_idle_regen,
    defeat_knockback_meters, roll_kill_resource,
)
from keyboards import hunt_kb
from states import Nav

router = Router()

ATTACK_BUTTON = InlineKeyboardButton(text="⚔️ Атака", callback_data="hunt_attack")

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
    """Достаёт (или создаёт по умолчанию) состояние боевых способностей из
    данных боя. Хранится прямо в monster_json/camp — сбрасывается автоматически
    при каждом новом бое, живёт весь текущий бой. Подставляет недостающие поля
    из дефолта (защита на случай неполных/старых сохранений)."""
    ab = data.get("abilities")
    if ab is None:
        ab = DEFAULT_ABILITIES_STATE.copy()
        data["abilities"] = ab
    else:
        for key, default_value in DEFAULT_ABILITIES_STATE.items():
            ab.setdefault(key, default_value)
    return ab


def _tick_ability_timers(abilities, consumed_sprint=False, consumed_mark_miss=False):
    """Уменьшает счётчики ходовых эффектов. Спринт/промах от метки
    расходуются только когда реально применились к этому действию (см.
    _resolve_player_hit), остальные тикают каждый ход."""
    if abilities["shield_cooldown"] > 0:
        abilities["shield_cooldown"] -= 1
    if abilities["fatigue_turns"] > 0 and not consumed_sprint:
        abilities["fatigue_turns"] -= 1


def _equipped_specials(user_id):
    special = database.get_special_mutations(user_id)
    return {k for k, v in special.items() if v["equipped"]}


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
        parts.append(f"🎯 Метка: ещё {abilities['mark_miss_turns']} промах(а)")
    elif abilities["mark_active"]:
        parts.append("🎯 Метка активна")
    return " | ".join(parts)


def _abilities_buttons(abilities, crab_type):
    shield_label = "🛡️ Щит" if abilities["shield_cooldown"] <= 0 else f"🛡️ Щит ({abilities['shield_cooldown']})"
    mark_label = "🎯 Метка" if not abilities["mark_used"] else "🎯 Метка (использована)"
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
    abilities = _get_abilities(monster)
    text = (
        f"<pre>{monster['art']}</pre>\n"
        f"<b>{monster['name']}</b>\n"
        f"❤️ Враг:  [{_hp_bar(monster['hp'], monster['max_hp'])}] {max(monster['hp'],0)}/{monster['max_hp']}\n"
        f"🦀 Ты:    [{_hp_bar(user_cur_hp, stats_max_hp)}] {max(user_cur_hp,0)}/{stats_max_hp}\n"
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
        status = "повержен" if camp["defeated"][i] else f"{max(guard['hp'],0)}/{guard['max_hp']} HP"
        text += f"{mark} {guard['name']} — {status}\n"
        if not camp["defeated"][i]:
            btn_text = f"🎯 {'Бить' if i == camp['current'] else 'Переключиться на'}: {guard['name']}"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"pick_guard_{i}")])
    current_guard = camp["guards"][camp["current"]]
    text += f"\n<pre>{current_guard['art']}</pre>\n"
    text += f"🦀 Ты: [{_hp_bar(user_cur_hp, stats_max_hp)}] {max(user_cur_hp,0)}/{stats_max_hp}\n"
    ab_status = _abilities_status_line(abilities, crab_type)
    if ab_status:
        text += f"{ab_status}\n"
    if last_line:
        text += f"\n{last_line}"
    buttons.append([ATTACK_BUTTON])
    buttons += _abilities_buttons(abilities, crab_type)
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


async def _push_battle_update(message, user_id, message_id, text, reply_markup=None):
    """Обновляет боевой экран. Сначала пробует отредактировать существующее
    сообщение. Если Telegram отвечает 'message is not modified' — это НЕ ошибка,
    а нормальный случай — тогда просто ничего не делаем. Только при НАСТОЯЩЕМ
    сбое шлём новое сообщение вместо того, чтобы молча падать."""
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id, message_id=message_id, text=text, reply_markup=reply_markup
        )
        return message_id
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return message_id
        sent = await message.answer(text, reply_markup=reply_markup)
        database.update_user(user_id, battle_message_id=sent.message_id)
        return sent.message_id
    except Exception:
        sent = await message.answer(text, reply_markup=reply_markup)
        database.update_user(user_id, battle_message_id=sent.message_id)
        return sent.message_id


async def perform_search(message: Message):
    """Общая логика 'Рыскать по дну'. Считаем всё (монстр/лагерь/статы/текст)
    ЗАРАНЕЕ, а слот охоты занимаем и монстра записываем ОДНИМ атомарным шагом
    (см. database.try_start_new_hunt) — так исключена ситуация 'слот занят,
    а монстра нет'."""
    user = database.get_user(message.from_user.id)
    stones = database.get_stones(message.from_user.id)
    mutations = database.get_mutations(message.from_user.id)
    stats = get_effective_stats(user, stones, mutations)
    now = int(time.time())
    healed_hp = apply_idle_regen(user, stats, now)
    crab_type = user["crab_type"]

    new_meters = next_monster_meters(user["cur_meters"])
    if is_guard_camp_meter(user["cur_meters"], new_meters):
        guards = roll_guard_camp(new_meters)
        camp = {
            "is_camp": True, "meters": new_meters, "guards": guards,
            "defeated": [False, False, False], "current": 0,
        }
        monster_json = json.dumps(camp)
        text, ikb = _render_camp(healed_hp, stats["max_hp"], camp, crab_type)
    else:
        monster = roll_monster(new_meters)
        monster["meters"] = new_meters
        monster_json = json.dumps(monster)
        text, ikb = _render_single(healed_hp, stats["max_hp"], monster, crab_type)

    started = database.try_start_new_hunt(message.from_user.id, monster_json, healed_hp, now)

    if not started:
        current = database.get_user(message.from_user.id)
        if current["in_hunt"] and current["monster_json"]:
            data = json.loads(current["monster_json"])
            if data.get("is_camp"):
                cur_text, cur_ikb = _render_camp(current["cur_hp"], stats["max_hp"], data, crab_type)
            else:
                cur_text, cur_ikb = _render_single(current["cur_hp"], stats["max_hp"], data, crab_type)
            if current["battle_message_id"]:
                await _push_battle_update(
                    message, message.from_user.id, current["battle_message_id"], cur_text, cur_ikb
                )
            else:
                sent = await message.answer(cur_text, reply_markup=hunt_kb(True))
                database.update_user(message.from_user.id, battle_message_id=sent.message_id)
                await _push_battle_update(message, message.from_user.id, sent.message_id, cur_text, cur_ikb)
            return

        database.update_user(message.from_user.id, in_hunt=0, monster_json=None)
        started = database.try_start_new_hunt(message.from_user.id, monster_json, healed_hp, now)

    if not started:
        fresh = database.get_user(message.from_user.id)
        await message.answer("Секунду...", reply_markup=hunt_kb(bool(fresh["in_hunt"])))
        return

    try:
        sent = await message.answer(text, reply_markup=hunt_kb(True))
        database.update_user(message.from_user.id, battle_message_id=sent.message_id)
        await _push_battle_update(message, message.from_user.id, sent.message_id, text, ikb)
    except Exception:
        database.update_user(message.from_user.id, in_hunt=0, monster_json=None)
        raise


@router.message(Nav.hunt, F.text == "🔎 Рыскать по дну")
async def search_enemy(message: Message, state: FSMContext):
    await perform_search(message)


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
    text, ikb = _render_camp(user["cur_hp"], stats["max_hp"], camp, user["crab_type"])
    await call.answer()
    try:
        await call.message.edit_text(text, reply_markup=ikb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            sent = await call.message.answer(text, reply_markup=ikb)
            database.update_user(call.from_user.id, battle_message_id=sent.message_id)
    except Exception:
        sent = await call.message.answer(text, reply_markup=ikb)
        database.update_user(call.from_user.id, battle_message_id=sent.message_id)


def _do_combat_round(target, stats, specials, log, force_crit=False, guaranteed_hit=False,
                      guaranteed_miss=False, dmg_multiplier=1.0, extra_miss_chance=0):
    """Одна серия ударов игрока по target (моб или страж).
    guaranteed_hit — шанс промаха не учитывается (например, во время Рывка).
    guaranteed_miss — удар гарантированно мимо (метка). dmg_multiplier — для
    Сокрушительного удара. extra_miss_chance — доп. шанс промаха (усталость
    после Рывка). Возвращает исцеление от вампиризма."""
    def do_hit(force_crit=force_crit):
        if guaranteed_miss:
            log.append("💨 Промах! (метка)")
            return False
        if guaranteed_hit:
            dmg = round(stats["damage"] * random.uniform(0.9, 1.1) * dmg_multiplier)
            is_crit = force_crit or (random.random() * 100 < stats["crit_chance"])
            if is_crit:
                dmg = round(dmg * stats["crit_damage"] / 100)
            missed = False
        else:
            dmg, is_crit, missed = player_attack(
                stats, monster_evasion=target["evasion"] + extra_miss_chance, force_crit=force_crit
            )
            dmg = round(dmg * dmg_multiplier)
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

    puncture_crit = "puncture" in specials and random.random() * 100 < SPECIAL_MUTATIONS["puncture"]["chance"]
    was_crit = do_hit(force_crit=(force_crit or puncture_crit))

    if target["hp"] > 0 and was_crit and "frenzy" in specials and random.random() * 100 < SPECIAL_MUTATIONS["frenzy"]["chance"]:
        log.append("🌀 Бешенство!")
        do_hit(force_crit=force_crit)

    return do_hit.heal


def _resolve_monster_counter(target, stats, specials, log, evasion_penalty=0, block_percent=0, guaranteed_dodge=False):
    """Ответный удар монстра. evasion_penalty — временное снижение уклонения
    (усталость после Рывка). block_percent — блокировка щитом. guaranteed_dodge —
    гарантированное уклонение (во время Рывка)."""
    if guaranteed_dodge:
        log.append("💨 Ты уворачиваешься на рывке!")
        return 0
    effective_stats = stats
    if evasion_penalty:
        effective_stats = dict(stats)
        effective_stats["evasion"] = max(0.0, stats["evasion"] - evasion_penalty)
    mdmg, dodged = monster_attack(target, effective_stats)
    camouflage_triggered = False
    if not dodged and "camouflage" in specials and random.random() * 100 < SPECIAL_MUTATIONS["camouflage"]["chance"]:
        dodged, mdmg, camouflage_triggered = True, 0, True
    if not dodged and block_percent:
        blocked = round(mdmg * block_percent / 100)
        mdmg -= blocked
        log.append(f"🛡️ Щит блокировал {blocked} урона!")
    if dodged:
        log.append("🌊 Уклонился!" if not camouflage_triggered else "🌊 Маскировка спасла!")
    else:
        log.append(f"Враг бьёт: -{mdmg}")
    return mdmg


async def _finish_turn(call, user_id, user, original_monster_json, data, is_camp, target,
                        stats, log, cur_hp):
    """Общий хвост обработки хода: проверка смерти цели (награда/лагерь) или
    смерти игрока (откат), либо просто сохранение состояния и обновление
    экрана. Переиспользуется атакой и всеми способностями.

    Бонус золота от Метки применяется здесь же, в момент ФАКТИЧЕСКОЙ выплаты —
    для одиночного моба это сразу при убийстве, а для лагеря стражей только
    при полной зачистке всех троих (награда там выдаётся одним пакетом), но
    флаг 'бонус заработан' взводится сразу на добивании помеченного стража и
    доживает до этого момента, даже если до общей выплаты ещё пара стражей."""
    message = call.message
    abilities = data.get("abilities", {})

    if target["hp"] <= 0:
        bonus_guard_index = None
        if abilities.get("mark_active"):
            abilities["mark_bonus_earned"] = True
            abilities["mark_active"] = False
            if is_camp:
                abilities["mark_bonus_guard_index"] = data["current"]
        if is_camp:
            bonus_guard_index = abilities.get("mark_bonus_guard_index")
        gold_extra_mult = MARK_ABILITY["gold_mult"] if abilities.get("mark_bonus_earned") else 1.0

        resource = roll_kill_resource()
        if is_camp:
            data["defeated"][data["current"]] = True
            remaining = [i for i, d in enumerate(data["defeated"]) if not d]
            if remaining:
                data["current"] = remaining[0]
                text, ikb = _render_camp(
                    cur_hp, stats["max_hp"], data, user["crab_type"],
                    last_line="\n".join(log) + "\n\n🎯 Выбери следующую цель.",
                )
                applied = database.try_apply_attack_result(
                    user_id, original_monster_json,
                    monster_json=json.dumps(data), cur_hp=cur_hp,
                )
                if not applied:
                    return
                await _push_battle_update(message, user_id, user["battle_message_id"], text, ikb)
                return
            # Бонус метки — точечно только на того стража, которого добили помеченным
            # (не на всю сумму!), даже если это случилось на 1-2 хода раньше финальной выплаты.
            total_gold = sum(
                round(gold_reward(g, stats, user) * (gold_extra_mult if i == bonus_guard_index else 1.0))
                for i, g in enumerate(data["guards"])
            )
            new_max_meters = max(user["max_meters"], data["meters"])
            applied = database.try_apply_attack_result(
                user_id, original_monster_json,
                in_hunt=0, monster_json=None, cur_hp=cur_hp,
                gold=user["gold"] + total_gold, kills=user["kills"] + 3,
                cur_meters=data["meters"], max_meters=new_max_meters,
                total_earned_gold=user["total_earned_gold"] + total_gold,
                last_hp_regen_ts=int(time.time()),
            )
            if not applied:
                return
            if resource:
                database.add_resource(user_id, resource)
            bonus_txt = " (учтён бонус 🎯 Метки на одного из стражей)" if bonus_guard_index is not None else ""
            final_text = "🏆 <b>Засада зачищена!</b>\n" + "\n".join(log) + f"\n\n💰 Получено золота за всех троих: {total_gold}{bonus_txt}"
            await _push_battle_update(message, user_id, user["battle_message_id"], final_text)
            await message.answer("Готов к новому рысканью по дну.", reply_markup=hunt_kb(False))
            return

        gold = round(gold_reward(data, stats, user) * gold_extra_mult)
        new_max_meters = max(user["max_meters"], data["meters"])
        applied = database.try_apply_attack_result(
            user_id, original_monster_json,
            in_hunt=0, monster_json=None, cur_hp=cur_hp,
            gold=user["gold"] + gold, kills=user["kills"] + 1,
            cur_meters=data["meters"], max_meters=new_max_meters,
            total_earned_gold=user["total_earned_gold"] + gold,
            last_hp_regen_ts=int(time.time()),
        )
        if not applied:
            return
        if resource:
            database.add_resource(user_id, resource)
        bonus_txt = " (×2 от 🎯 Метки)" if gold_extra_mult != 1.0 else ""
        final_text = "🏆 <b>Победа!</b>\n" + "\n".join(log) + f"\n\n💰 Золото: {gold}{bonus_txt}"
        await _push_battle_update(message, user_id, user["battle_message_id"], final_text)
        await message.answer("Готов к новому рысканью по дну.", reply_markup=hunt_kb(False))
        return

    last_line = "\n".join(log)

    if cur_hp <= 0:
        knock_to = defeat_knockback_meters(user["cur_meters"])
        recovered_hp = stats["max_hp"]
        applied = database.try_apply_attack_result(
            user_id, original_monster_json,
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
        await _push_battle_update(message, user_id, user["battle_message_id"], final_text)
        await message.answer("Можешь продолжать рыскать по дну.", reply_markup=hunt_kb(False))
        return

    if is_camp:
        text, ikb = _render_camp(cur_hp, stats["max_hp"], data, user["crab_type"], last_line=last_line)
    else:
        text, ikb = _render_single(cur_hp, stats["max_hp"], data, user["crab_type"], last_line=last_line)

    applied = database.try_apply_attack_result(
        user_id, original_monster_json,
        cur_hp=cur_hp, monster_json=json.dumps(data),
    )
    if not applied:
        return
    await _push_battle_update(message, user_id, user["battle_message_id"], text, ikb)


def _load_battle_context(user_id):
    user = database.get_user(user_id)
    if not user["in_hunt"] or not user["monster_json"]:
        return None
    stones = database.get_stones(user_id)
    mutations = database.get_mutations(user_id)
    stats = get_effective_stats(user, stones, mutations)
    specials = _equipped_specials(user_id)
    original_monster_json = user["monster_json"]
    data = json.loads(original_monster_json)
    is_camp = data.get("is_camp", False)
    target = data["guards"][data["current"]] if is_camp else data
    abilities = _get_abilities(data)
    return user, stats, specials, original_monster_json, data, is_camp, target, abilities


@router.callback_query(F.data == "hunt_attack")
async def attack(call: CallbackQuery):
    user_id = call.from_user.id
    ctx = _load_battle_context(user_id)
    if not ctx:
        await call.answer("Сейчас не с кем сражаться. Нажми «🔎 Рыскать по дну».", show_alert=True)
        return
    user, stats, specials, original_monster_json, data, is_camp, target, abilities = ctx
    await call.answer()

    log = []
    cur_hp = user["cur_hp"]

    # Модификаторы от активных способностей
    consumed_sprint = abilities["sprint_turns"] > 0
    guaranteed_hit = consumed_sprint
    consumed_mark_miss = (not consumed_sprint) and abilities["mark_miss_turns"] > 0
    guaranteed_miss = consumed_mark_miss
    force_crit = abilities["rage_active"]

    heal = _do_combat_round(
        target, stats, specials, log,
        force_crit=force_crit, guaranteed_hit=guaranteed_hit, guaranteed_miss=guaranteed_miss,
        extra_miss_chance=(UNIQUE_ABILITIES[2]["fatigue_miss_bonus"] if abilities["fatigue_turns"] > 0 else 0),
    )
    cur_hp = min(stats["max_hp"], cur_hp + heal)

    if abilities["rage_active"]:
        self_dmg = round(stats["max_hp"] * UNIQUE_ABILITIES[3]["self_damage_percent"] / 100)
        cur_hp -= self_dmg
        log.append(f"🩸 Раж отбирает {self_dmg} прочности")

    if consumed_sprint:
        abilities["sprint_turns"] -= 1
        if abilities["sprint_turns"] == 0:
            abilities["fatigue_turns"] = UNIQUE_ABILITIES[2]["fatigue_turns"]
    if consumed_mark_miss:
        abilities["mark_miss_turns"] -= 1
    _tick_ability_timers(abilities, consumed_sprint=consumed_sprint)

    if target["hp"] > 0 and cur_hp > 0:
        evasion_penalty = UNIQUE_ABILITIES[2]["fatigue_evasion_penalty"] if abilities["fatigue_turns"] > 0 else 0
        mdmg = _resolve_monster_counter(
            target, stats, specials, log, evasion_penalty=evasion_penalty, guaranteed_dodge=consumed_sprint
        )
        cur_hp -= mdmg

    await _finish_turn(call, user_id, user, original_monster_json, data, is_camp, target,
                       stats, log, cur_hp)


@router.callback_query(F.data == "ability_shield")
async def ability_shield(call: CallbackQuery):
    user_id = call.from_user.id
    ctx = _load_battle_context(user_id)
    if not ctx:
        await call.answer("Сейчас не с кем сражаться.", show_alert=True)
        return
    user, stats, specials, original_monster_json, data, is_camp, target, abilities = ctx

    if abilities["shield_cooldown"] > 0:
        await call.answer(f"Щит перезаряжается ещё {abilities['shield_cooldown']} х.", show_alert=True)
        return
    await call.answer()

    log = ["🛡️ Ты поднимаешь щит!"]
    cur_hp = user["cur_hp"]

    if target.get("poison_turns", 0) > 0:
        target["hp"] -= target["poison_dmg"]
        target["poison_turns"] -= 1
        log.append(f"☠️ Яд: -{target['poison_dmg']}")

    _tick_ability_timers(abilities)
    abilities["shield_cooldown"] = SHIELD_ABILITY["cooldown_turns"]

    if target["hp"] > 0:
        mdmg = _resolve_monster_counter(
            target, stats, specials, log, block_percent=SHIELD_ABILITY["block_percent"]
        )
        cur_hp -= mdmg

    await _finish_turn(call, user_id, user, original_monster_json, data, is_camp, target, stats, log, cur_hp)


@router.callback_query(F.data == "ability_mark")
async def ability_mark(call: CallbackQuery):
    user_id = call.from_user.id
    ctx = _load_battle_context(user_id)
    if not ctx:
        await call.answer("Сейчас не с кем сражаться.", show_alert=True)
        return
    user, stats, specials, original_monster_json, data, is_camp, target, abilities = ctx

    if abilities["mark_used"]:
        await call.answer("Метка уже использована в этом бою.", show_alert=True)
        return
    await call.answer()

    log = ["🎯 Ты метишь врага! Следующие 2 удара промахнутся, но добивание даст ×2 золота."]
    cur_hp = user["cur_hp"]

    if target.get("poison_turns", 0) > 0:
        target["hp"] -= target["poison_dmg"]
        target["poison_turns"] -= 1
        log.append(f"☠️ Яд: -{target['poison_dmg']}")

    abilities["mark_used"] = True
    abilities["mark_active"] = True
    abilities["mark_miss_turns"] = MARK_ABILITY["miss_turns"]
    _tick_ability_timers(abilities)

    if target["hp"] > 0:
        mdmg = _resolve_monster_counter(target, stats, specials, log)
        cur_hp -= mdmg

    await _finish_turn(call, user_id, user, original_monster_json, data, is_camp, target, stats, log, cur_hp)


@router.callback_query(F.data == "ability_unique")
async def ability_unique(call: CallbackQuery):
    user_id = call.from_user.id
    ctx = _load_battle_context(user_id)
    if not ctx:
        await call.answer("Сейчас не с кем сражаться.", show_alert=True)
        return
    user, stats, specials, original_monster_json, data, is_camp, target, abilities = ctx

    if abilities["unique_used"]:
        await call.answer("Уникальная способность уже использована в этом бою.", show_alert=True)
        return
    await call.answer()

    crab_type = user["crab_type"]
    ability = UNIQUE_ABILITIES.get(crab_type, UNIQUE_ABILITIES[1])
    abilities["unique_used"] = True
    cur_hp = user["cur_hp"]
    log = [f"{ability['name']}!"]

    if crab_type == 1:
        # Панцирник: сокрушительный удар — x3 урона, но 15% своей прочности в отдачу
        heal = _do_combat_round(target, stats, specials, log, dmg_multiplier=ability["damage_mult"])
        cur_hp = min(stats["max_hp"], cur_hp + heal)
        self_dmg = round(stats["max_hp"] * ability["self_damage_percent"] / 100)
        cur_hp -= self_dmg
        log.append(f"💥 Отдача: -{self_dmg} прочности")
        _tick_ability_timers(abilities)
        if target["hp"] > 0 and cur_hp > 0:
            mdmg = _resolve_monster_counter(target, stats, specials, log)
            cur_hp -= mdmg

    elif crab_type == 2:
        # Быстроход: рывок — активация без урона, монстр не успевает ответить
        abilities["sprint_turns"] = ability["sprint_turns"]
        log.append("💨 Ты срываешься с места — враг не успевает ответить!")
        _tick_ability_timers(abilities)

    elif crab_type == 3:
        # Крит-краб: кровавый раж — этот и все следующие удары critical,
        # но каждый удар стоит прочности
        abilities["rage_active"] = True
        heal = _do_combat_round(target, stats, specials, log, force_crit=True)
        cur_hp = min(stats["max_hp"], cur_hp + heal)
        self_dmg = round(stats["max_hp"] * ability["self_damage_percent"] / 100)
        cur_hp -= self_dmg
        log.append(f"🩸 Раж отбирает {self_dmg} прочности")
        _tick_ability_timers(abilities)
        if target["hp"] > 0 and cur_hp > 0:
            mdmg = _resolve_monster_counter(target, stats, specials, log)
            cur_hp -= mdmg
    else:
        _tick_ability_timers(abilities)

    await _finish_turn(call, user_id, user, original_monster_json, data, is_camp, target,
                       stats, log, cur_hp)


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
