# -*- coding: utf-8 -*-
"""
Все формулы баланса собраны здесь.
"""
import random
import json

from data import (
    CRABS, PASSIVE_MUTATIONS, ACTIVE_MUTATIONS, EVOLUTION_NODES, EVENT_CHESTS,
    STONE_COLORS, STONE_EFFECT_BONUS, STONE_LEVEL_CHANCE,
    MYTHIC_EVENT_UNLOCK_MOLTS, MYTHIC_EVENT_UNLOCK_MAX_METERS, MYTHIC_EVENT_UNLOCK_KILLS,
    MONSTERS, DEPTH_ZONES, DEPTH_BARRIERS, MOLT_RANKS, PLAYER_MISS_CHANCE,
    GUARD_CAMP_INTERVAL, GUARD_CAMP_ELITE_MULT, ELITE_ENCOUNTER_INTERVAL, ELITE_ENCOUNTER_MULT,
    DIG_STONES_PER_HOUR, RESOURCE_DROP_CHANCE_KILL, RESOURCE_DROP_CHANCE_DIG, RESOURCES,
    PERMANENT_BOOST_MULT,
)

MOLT_UNLOCK_LEVEL = 100

def can_molt(crab_level: int) -> bool:
    return crab_level >= MOLT_UNLOCK_LEVEL

def calculate_dna_reward(crab_level: int) -> int:
    if crab_level < MOLT_UNLOCK_LEVEL: return 0
    return int((crab_level / 4.0) ** 1.5)

def get_mutation_cost(purchased_count: int) -> int:
    base_prices = [10, 25, 50, 85, 130]
    if purchased_count < len(base_prices): return base_prices[purchased_count]
    cost = base_prices[-1]
    extra_purchases = purchased_count - len(base_prices) + 1
    for _ in range(extra_purchases): cost = int(cost * 1.5)
    return cost

def level_up_cost(current_level, molts):
    base = 6 * (current_level ** 1.35)
    molt_scale = 1 + molts * 0.4
    return max(5, round(base * molt_scale))

def total_mutation_levels(mutations_v3):
    """Суммарный уровень ВСЕХ мутаций в инвентаре (для барьеров)."""
    if not mutations_v3: return 0
    return sum(m.get("level", 0) for m in mutations_v3)

def get_blocking_barrier(current_meters, mutations_v3):
    total = total_mutation_levels(mutations_v3)
    for barrier_meters, required in DEPTH_BARRIERS:
        if current_meters >= barrier_meters and total < required:
            return barrier_meters, required
    return None

def next_monster_meters(current_meters, mutations_v3=None):
    step = 1
    new_meters = current_meters + step
    if mutations_v3 is None: return new_meters
    total = total_mutation_levels(mutations_v3)
    for barrier_meters, required in DEPTH_BARRIERS:
        if current_meters < barrier_meters <= new_meters and total < required: return barrier_meters
        if current_meters >= barrier_meters and total < required: return current_meters 
    return new_meters

def _base_monster_numbers(meters):
    hp = 12 + meters * 2.6 + meters ** 1.12
    dmg = 2 + meters * 0.55 + (meters ** 1.05) * 0.08
    gold = 5 + meters * 1.5 + (meters ** 1.08) * 0.25
    return hp, dmg, gold

def eligible_monsters(meters):
    pool = [m for m in MONSTERS if m["min_meters"] <= meters <= m.get("max_meters", float("inf"))]
    return pool or [MONSTERS[0]]

def roll_monster(meters, elite_mult=1.0):
    pool = eligible_monsters(meters)
    weights = [m.get("weight", 10) for m in pool]
    species = random.choices(pool, weights=weights, k=1)[0]
    hp_base, dmg_base, gold_base = _base_monster_numbers(meters)
    hp = max(1, round(hp_base * species["hp_mult"] * elite_mult))
    dmg = max(1, round(dmg_base * species["dmg_mult"] * elite_mult))
    gold = max(1, round(gold_base * species["gold_mult"] * elite_mult))
    return {
        "key": species["key"], "name": species["name"], "art": species["art"], "evasion": species["evasion"],
        "hp": hp, "max_hp": hp, "dmg": dmg, "gold": gold, "poison_turns": 0, "poison_dmg": 0,
    }

def is_guard_camp_meter(previous_meters, new_meters): return (new_meters // GUARD_CAMP_INTERVAL) > (previous_meters // GUARD_CAMP_INTERVAL)
def roll_guard_camp(meters): return [roll_monster(meters, elite_mult=GUARD_CAMP_ELITE_MULT) for _ in range(3)]
def is_elite_encounter_meter(previous_meters, new_meters): return (new_meters // ELITE_ENCOUNTER_INTERVAL) > (previous_meters // ELITE_ENCOUNTER_INTERVAL)

def get_depth_zone_name(meters):
    name = DEPTH_ZONES[0][1]
    for threshold, zone_name in DEPTH_ZONES:
        if meters >= threshold: name = zone_name
        else: break
    return name

def get_molt_rank(molts):
    name = MOLT_RANKS[0][1]
    for threshold, rank_name in MOLT_RANKS:
        if molts >= threshold: name = rank_name
        else: break
    return name

def roll_dig_loot(hours):
    n = max(1, round(hours * DIG_STONES_PER_HOUR * random.uniform(0.85, 1.15)))
    loot = []
    colors = list(STONE_COLORS.keys())
    for _ in range(n):
        color = random.choice(colors)
        roll = random.random()
        acc = 0; level = 1
        for lvl, chance in sorted(STONE_LEVEL_CHANCE.items()):
            acc += chance
            if roll <= acc:
                level = lvl; break
        loot.append((color, level))
    return loot

def roll_dig_resources(hours):
    found = []
    ticks = max(1, round(hours))
    for _ in range(ticks):
        if random.random() < RESOURCE_DROP_CHANCE_DIG: found.append(random.choice(list(RESOURCES.keys())))
    return found

def roll_kill_resource():
    if random.random() < RESOURCE_DROP_CHANCE_KILL: return random.choice(list(RESOURCES.keys()))
    return None


# ================== ЯДРО СТАТОВ V3 ==================
def get_effective_stats(user, stones, mutations_v3=None):
    crab_base = CRABS[user["crab_type"]]
    user_crystal = crab_base["crystal"]
    
    # 1. Базовые статы краба
    stats = {
        "damage": float(crab_base["damage"]),
        "evasion": float(crab_base["evasion"]),
        "luck": float(crab_base["luck"]),
        "crit_chance": float(crab_base["crit_chance"]),
        "crit_damage": float(crab_base["crit_damage"]),
        "max_hp": float(crab_base["max_hp"]),
    }

    # Плоские прибавки за уровень краба и камни
    stats["damage"] += user["crab_level"] * 1.4
    stats["max_hp"] += user["crab_level"] * 4.5

    for st in stones:
        effect = STONE_COLORS[st["color"]]["effect"]
        bonus = STONE_EFFECT_BONUS[effect][st["level"]] * st["count"]
        stats[effect] += bonus

    # 2. Множители
    multipliers = {"mult_damage": 1.0, "mult_hp": 1.0, "mult_evasion": 1.0}

    # 3. Применяем Древо Эволюции
    try: evo_tree = json.loads(user.get("evolution_tree", "[]"))
    except: evo_tree = []
        
    for node_key in evo_tree:
        node = EVOLUTION_NODES.get(node_key)
        if node:
            stat_name = node["buff_stat"]
            if stat_name.startswith("mult_"): multipliers[stat_name] += node["buff_val"]
            elif stat_name.startswith("flat_"): stats[stat_name.replace("flat_", "")] += node["buff_val"]

    # 4. Применяем Пассивные Кристальные Мутации
    if mutations_v3:
        for mut in mutations_v3:
            if mut["is_active"] == 0: 
                p_data = PASSIVE_MUTATIONS.get(mut["variant_key"])
                if not p_data: continue
                lvl = mut["level"]
                for st, val in p_data.get("base_buff", {}).items(): stats[st] += val * lvl
                
                if p_data["crystal"] == user_crystal:
                    for st, val in p_data.get("synergy_buff", {}).items():
                        if st.startswith("mult_"): multipliers[st] += val * lvl
                        elif st.startswith("flat_"): stats[st.replace("flat_", "")] += val * lvl

    # 5. Умножаем базовые статы на собранные множители
    stats["damage"] *= multipliers["mult_damage"]
    stats["max_hp"] *= multipliers["mult_hp"]
    stats["evasion"] *= multipliers["mult_evasion"]

    # 6. Применяем дебаффы от надетых Активных Мутаций
    if mutations_v3:
        for mut in mutations_v3:
            if mut["is_active"] == 1 and mut["equipped"] == 1:
                a_data = ACTIVE_MUTATIONS.get(mut["variant_key"])
                if not a_data: continue
                for st, penalty in a_data.get("debuff", {}).items():
                    if st.startswith("mult_"): stats[st.replace("mult_", "")] *= (1.0 - penalty)
                    else: stats[st] *= (1.0 - penalty)

    # Жесткие ограничения
    stats["evasion"] = max(0.0, min(stats["evasion"], 75.0))
    stats["crit_chance"] = max(0.0, min(stats["crit_chance"], 90.0))
    stats["damage"] = max(1.0, stats["damage"])
    stats["max_hp"] = max(10, round(stats["max_hp"]))

    if user.get("buff_expires_ts") and user.get("buff_damage_mult"):
        import time
        if user["buff_expires_ts"] > int(time.time()):
            stats["damage"] *= user["buff_damage_mult"]

    return stats


def get_equipped_special_effects(mutations_v3):
    """Возвращает set всех особых эффектов (poison, puncture и т.д.) от надетых активных мутаций."""
    specials = set()
    if not mutations_v3: return specials
    
    for m in mutations_v3:
        if m.get("is_active") == 1 and m.get("equipped") == 1:
            variant = ACTIVE_MUTATIONS.get(m["variant_key"])
            if variant and variant.get("special_effect"):
                specials.add(variant["special_effect"])
    return specials

# ====================================================

def roll_chest_loot(chest_type, owned_variant_keys):
    chest_data = EVENT_CHESTS.get(chest_type, EVENT_CHESTS["default"])
    loot = {"shells": chest_data.get("shells", 0), "stones": [], "mutation": None}
    colors = list(STONE_COLORS.keys())
    for _ in range(chest_data.get("stones", 0)):
        color = random.choice(colors)
        loot["stones"].append((color, chest_data.get("stone_lvl", 3)))
        
    if random.random() * 100 <= chest_data.get("mut_chance", 0.0):
        possible_muts = []
        for key, v in ACTIVE_MUTATIONS.items():
            if key not in owned_variant_keys:
                possible_muts.append({"key": key, "slot": v["slot"], "name": v["name"]})
        if possible_muts: loot["mutation"] = random.choice(possible_muts)
    return loot

def player_attack(stats, monster_evasion=0, force_crit=False):
    if random.random() * 100 < (PLAYER_MISS_CHANCE + monster_evasion): return 0, False, True
    dmg = stats["damage"] * random.uniform(0.9, 1.1)
    is_crit = force_crit or (random.random() * 100 < stats["crit_chance"])
    if is_crit: dmg *= stats["crit_damage"] / 100
    return round(dmg), is_crit, False

def monster_attack(monster, stats):
    if random.random() * 100 < stats["evasion"]: return 0, True
    dmg = monster["dmg"] * random.uniform(0.85, 1.15)
    return round(dmg), False

def gold_reward(monster, stats, user=None):
    mult = 1 + stats["luck"] / 100
    amount = max(1, round(monster["gold"] * mult))
    return apply_permanent_boost(amount, user)

def apply_permanent_boost(amount, user):
    if user and user.get("permanent_boost"): return round(amount * PERMANENT_BOOST_MULT)
    return amount

def apply_idle_regen(user, stats, now):
    if user["cur_hp"] >= stats["max_hp"]: return stats["max_hp"]
    last_ts = user["last_hp_regen_ts"] or now
    elapsed_minutes = max(0, (now - last_ts) / 60)
    heal_fraction = min(1.0, elapsed_minutes / 30)
    missing = stats["max_hp"] - user["cur_hp"]
    healed = missing * heal_fraction
    return min(stats["max_hp"], round(user["cur_hp"] + healed))

def defeat_knockback_meters(cur_meters): return max(1, cur_meters - 1)

def weighted_sample_without_replacement(items, weights, k):
    pool = list(zip(items, weights))
    result = []
    for _ in range(min(k, len(pool))):
        total = sum(w for _, w in pool)
        if total <= 0: break
        r = random.uniform(0, total)
        upto = 0
        for i, (it, w) in enumerate(pool):
            upto += w
            if upto >= r:
                result.append(it)
                pool.pop(i)
                break
    return result

def shop_gold_reward(user, levels_worth):
    cost = level_up_cost(user["crab_level"], user["molts"])
    return max(50, round(cost * levels_worth))

def shop_dna_reward(mutations_v3, upgrades_worth):
    avg_level = 1
    if mutations_v3:
        total_lvls = sum(m.get("level", 0) for m in mutations_v3)
        avg_level = max(1, total_lvls // max(1, len(mutations_v3)))
    return max(5, round(cost_upgrade_mutation(avg_level) * upgrades_worth))

def mythic_events_unlocked(user):
    return (user["molts"] >= MYTHIC_EVENT_UNLOCK_MOLTS or user["max_meters"] >= MYTHIC_EVENT_UNLOCK_MAX_METERS or user["kills"] >= MYTHIC_EVENT_UNLOCK_KILLS)

def format_number(num: int) -> str:
    if num < 0: return str(num)
    if num >= 1_000_000_000_000_000: return f"{num / 1_000_000_000_000_000:.1f}кв".replace(".0кв", "кв")
    if num >= 1_000_000_000_000: return f"{num / 1_000_000_000_000:.1f}т".replace(".0т", "т")
    if num >= 1_000_000_000: return f"{num / 1_000_000_000:.1f}б".replace(".0б", "б")
    if num >= 1_000_000: return f"{num / 1_000_000:.1f}м".replace(".0м", "м")
    if num >= 1_000: return f"{num / 1_000:.1f}к".replace(".0к", "к")
    return str(num)

def cost_upgrade_mutation(current_level): return max(10, round(15 * (current_level ** 1.4)))
