async def _finish_turn(call, user_id, fsm_data, state: FSMContext, is_camp, target, log):
    message = call.message
    cur_hp = fsm_data["cur_hp"]
    monster = fsm_data["monster"]
    stats = fsm_data["stats"]
    abilities = fsm_data["abilities"]
    specials = fsm_data["specials"]
    msg_id = fsm_data.get("battle_message_id", message.message_id)
    
    last_line = "\n".join(log)
    redis_client = state.storage.redis
    now = int(time.time())

    # 1. Краб погиб
    if cur_hp <= 0:
        await database.flush_user_buffer(redis_client, user_id)
        user_db = await database.run_async(database.get_user, user_id)
        recovered_hp = stats["max_hp"]
        
        if target.get("is_boss"):
            await database.run_async(database.add_event_damage, target["event_id"], user_id, target["accumulated_damage"])
            cooldown_ts = int(time.time()) + int(3.5 * 3600)
            
            await database.run_async(
                database.update_user, user_id,
                cur_hp=recovered_hp, last_hp_regen_ts=now, boss_cooldown_ts=cooldown_ts
            )
            
            final_text = (
                f"☠️ <b>Босс сокрушил тебя!</b>\n"
                f"Ты нанёс <b>{format_number(target['accumulated_damage'])}</b> урона (сохранено в рейтинге).\n"
                f"Твой панцирь разбит, нужно 3.5 часа на восстановление.\n\n" + last_line
            )
            await state.set_data({})
            await _push_battle_update(message, user_id, msg_id, final_text)
            await message.answer("Обычная охота всё ещё доступна.", reply_markup=hunt_kb(False))
            return
        else:
            knock_to = defeat_knockback_meters(user_db["cur_meters"])
            await database.run_async(
                database.update_user, user_id,
                cur_hp=recovered_hp, cur_meters=knock_to, last_hp_regen_ts=now
            )
            
            final_text = (
                f"💔 <b>Панцирь треснул!</b> Тебя отбросило назад до {format_number(knock_to)} м.\n"
                f"Прочность восстановлена полностью — можешь пробовать снова.\n\n" + last_line
            )
            await state.set_data({})
            await _push_battle_update(message, user_id, msg_id, final_text)
            await message.answer("Можешь продолжать рыскать по дну.", reply_markup=hunt_kb(False))
            return

    # 2. Враг побежден
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
        
        # Засада стражей
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
            if "greed" in specials and random.random() * 100 < 15:
                total_gold *= 2
                log.append("🪙 Жадный панцирь удвоил золото!")
                
            last_line = "\n".join(log)
            new_meters = monster["meters"]
            new_max_meters = max(user_db["max_meters"], new_meters)
            
            await database.add_to_buffer(
                redis_client, user_id, gold=total_gold, kills=3, 
                cur_meters=new_meters, max_meters=new_max_meters,
                cur_hp=cur_hp, last_hp_regen_ts=now
            )

            if resource:
                await database.flush_user_buffer(redis_client, user_id)
                await database.run_async(database.add_resource, user_id, resource)
            
            bonus_txt = " (учтён бонус 🪝 Проклятия)" if bonus_guard_index is not None else ""
            final_text = "🏆 <b>Засада зачищена!</b>\n" + last_line + f"\n\n💰 Получено золота: {format_number(total_gold)}{bonus_txt}"
            await state.set_data({})
            await _push_battle_update(message, user_id, msg_id, final_text)
            await message.answer("Готов к новому рысканью по дну.", reply_markup=hunt_kb(False))
            return

        # Обычный монстр
        gold = round(gold_reward(monster, stats, user_db) * gold_extra_mult)
        if "greed" in specials and random.random() * 100 < 15:
            gold *= 2
            log.append("🪙 Жадный панцирь удвоил золото!")
            
        last_line = "\n".join(log)
        new_meters = monster["meters"]
        new_max_meters = max(user_db["max_meters"], new_meters)
        
        await database.add_to_buffer(
            redis_client, user_id, gold=gold, kills=1, 
            cur_meters=new_meters, max_meters=new_max_meters,
            cur_hp=cur_hp, last_hp_regen_ts=now
        )
        
        if resource:
            await database.flush_user_buffer(redis_client, user_id)
            await database.run_async(database.add_resource, user_id, resource)
        
        bonus_txt = " (×2 от 🪝 Проклятия)" if gold_extra_mult != 1.0 else ""
        final_text = "🏆 <b>Победа!</b>\n" + last_line + f"\n\n💰 Золото: {format_number(gold)}{bonus_txt}"
        await state.set_data({})
        await _push_battle_update(message, user_id, msg_id, final_text)
        await message.answer("Готов к новому рысканью по дну.", reply_markup=hunt_kb(False))
        return

    # 3. Бой продолжается
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
    data = await state.get_data()
    msg_id = data.get("battle_message_id")
    cur_hp = data.get("cur_hp")
    monster = data.get("monster")
    
    redis_client = state.storage.redis
    user_id = message.from_user.id
    
    if monster and monster.get("is_boss") and monster.get("accumulated_damage", 0) > 0:
        await database.run_async(database.add_event_damage, monster["event_id"], user_id, monster["accumulated_damage"])

    if cur_hp is not None:
        await database.add_to_buffer(redis_client, user_id, cur_hp=cur_hp, last_hp_regen_ts=int(time.time()))
    
    await database.flush_user_buffer(redis_client, user_id)
    await state.set_data({})
        
    if msg_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id, message_id=msg_id,
                text="↩️ Ты ушёл боком, сохранив позицию и прочность. Награды не будет.",
            )
        except Exception:
            pass
            
    await message.answer(
        "Позиция сохранена, награды не будет. Прочность восстановится сама.",
        reply_markup=hunt_kb(False),
    )
