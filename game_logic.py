# -*- coding: utf-8 -*-
"""
Все формулы баланса собраны здесь.
"""
import random

from data import (
    CRABS, MUTATION_SLOT_BASE_COST, MUTATION_VARIANTS, EVENT_CHESTS,
    STONE_COLORS, STONE_EFFECT_BONUS, STONE_LEVEL_CHANCE,
    MYTHIC_EVENT_UNLOCK_MOLTS, MYTHIC_EVENT_UNLOCK_MAX_METERS, MYTHIC_EVENT_UNLOCK_KILLS,
    MONSTERS, DEPTH_ZONES, DEPTH_BARRIERS, MOLT_RANKS, PLAYER_MISS_CHANCE,
    GUARD_CAMP_INTERVAL, GUARD_CAMP_ELITE_MULT, ELITE_ENCOUNTER_INTERVAL, ELITE_ENCOUNTER_MULT,
    DIG_STONES_PER_HOUR, RESOURCE_DROP_CHANCE_KILL, RESOURCE_DROP_CHANCE_DIG, RESOURCES,
    PERMANENT_BOOST_MULT,
)

MOLT_BASE_LEVEL = 70
MOLT_LEVEL_STEP = 15


def molt_required_level(molts):
    return MOLT_BASE_LEVEL + molts * MOLT_LEVEL_STEP


def level_up_cost(current_level, molts):
    base = 6 * (current_level ** 1.35)
    molt_scale = 1 + molts * 0.4
    return max(5, round(base * molt_scale))


def dna_points_for_molt(molts, crab_level):
    required = molt_required_level(molts)
    base = 14 * (1.45 ** molts)
    over_levels = max(0, crab_level - required)
    bonus = over_levels * 1.0
    return round(base + bonus)


def roll_mutation_variant(slot):
    return random.choice(MUTATION_VARIANTS[slot])


def get_mutation_variant(slot, variant_key):
    for v in MUTATION_VARIANTS.get(slot, []):
        if v["key"] == variant_key:
            return v
    return None


# ---------------- Монстры ----------------

def total_mutation_levels(mutations):
    """Суммарный уровень ВСЕХ купленных мутаций."""
    if not mutations:
        return 0
    if isinstance(mutations, list):
        return sum(m.get("level", 0) for m in mutations)
    return sum(m.get("level", 0) for m in mutations.values())


def get_blocking_barrier(current_meters, mutations):
    total = total_mutation_levels(mutations)
    for barrier_meters, required in DEPTH_BARRIERS:
        if current_meters >= barrier_meters and total < required:
            return barrier_meters, required
    return None


def next_monster_meters(current_meters, mutations=None):
    step = 1
    new_meters = current_meters + step
    if mutations is None:
        return new_meters

    total = total_mutation_levels(mutations)
    for barrier_meters, required in DEPTH_BARRIERS:
        if current_meters < barrier_meters <= new_meters and total < required:
            return barrier_meters
        if current_meters >= barrier_meters and total < required:
            return current_meters 
    return new_meters


def _base_monster_numbers(meters):
    hp = 12 + meters * 2.6 + meters ** 1.12
    dmg = 2 + meters * 0.55 + (meters ** 1.05) * 0.08
    gold = 5 + meters * 1.5 + (meters ** 1.08) * 0.25
    return hp, dmg, gold


def eligible_monsters(meters):
    pool = [
        m for m in MONSTERS
        if m["min_meters"] <= meters <= m.get("max_meters", float("inf"))
    ]
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
        "key": species["key"], "name": species["name"], "art": species["art"],
        "evasion": species["evasion"],
        "hp": hp, "max_hp": hp, "dmg": dmg, "gold": gold,
        "poison_turns": 0, "poison_dmg": 0,
    }


def is_guard_camp_meter(previous_meters, new_meters):
    return (new_meters // GUARD_CAMP_INTERVAL) > (previous_meters // GUARD_CAMP_INTERVAL)


def roll_guard_camp(meters):
    return [roll_monster(meters, elite_mult=GUARD_CAMP_ELITE_MULT) for _ in range(3)]


def is_elite_encounter_meter(previous_meters, new_meters):
    return (new_meters // ELITE_ENCOUNTER_INTERVAL) > (previous_meters // ELITE_ENCOUNTER_INTERVAL)


def get_depth_zone_name(meters):
    name = DEPTH_ZONES[0][1]
    for threshold, zone_name in DEPTH_ZONES:
        if meters >= threshold:
            name = zone_name
        else:
            break
    return name


def get_molt_rank(molts):
    name = MOLT_RANKS[0][1]
    for threshold, rank_name in MOLT_RANKS:
        if molts >= threshold:
            name = rank_name
        else:
            break
    return name


def roll_dig_loot(hours):
    n = max(1, round(hours * DIG_STONES_PER_HOUR * random.uniform(0.85, 1.15)))
    loot = []
    colors = list(STONE_COLORS.keys())
    for _ in range(n):
        color = random.choice(colors)
        roll = random.random()
        acc = 0
        level = 1
        for lvl, chance in sorted(STONE_LEVEL_CHANCE.items()):
            acc += chance
            if roll <= acc:
                level = lvl
                break
        loot.append((color, level))
    return loot


def roll_dig_resources(hours):
    found = []
    ticks = max(1, round(hours))
    for _ in range(ticks):
        if random.random() < RESOURCE_DROP_CHANCE_DIG:
            found.append(random.choice(list(RESOURCES.keys())))
    return found


def roll_kill_resource():
    if random.random() < RESOURCE_DROP_CHANCE_KILL:
        return random.choice(list(RESOURCES.keys()))
    return None


def get_effective_stats(user, stones, mutations=None):
    crab_base = CRABS[user["crab_type"]]
    stats = {
        "damage": float(crab_base["damage"]),
        "evasion": float(crab_base["evasion"]),
        "luck": float(crab_base["luck"]),
        "crit_chance": float(crab_base["crit_chance"]),
        "crit_damage": float(crab_base["crit_damage"]),
        "max_hp": float(crab_base["max_hp"]),
    }

    stats["damage"] += user["crab_level"] * 1.4
    stats["max_hp"] += user["crab_level"] * 4.5

    for st in stones:
        effect = STONE_COLORS[st["color"]]["effect"]
        bonus = STONE_EFFECT_BONUS[effect][st["level"]] * st["count"]
        stats[effect] += bonus

    if mutations:
        mut_list = mutations if isinstance(mutations, list) else [{"slot": k, **v} for k, v in mutations.items()]
        for m in mut_list:
            if not (m and m.get("equipped") and m.get("level", 0) > 0 and m.get("variant_key")):
                continue
            variant = get_mutation_variant(m["slot"], m["variant_key"])
            if not variant:
                continue
            level = m["level"]
            stats[variant["buff_stat"]] += variant["buff_per_level"] * level
            stats[variant["debuff_stat"]] -= variant["debuff_per_level"] * level

    stats["evasion"] = max(0.0, min(stats["evasion"], 75.0))
    stats["crit_chance"] = max(0.0, min(stats["crit_chance"], 90.0))
    stats["damage"] = max(1.0, stats["damage"])
    stats["max_hp"] = max(10, round(stats["max_hp"]))

    if user.get("buff_expires_ts") and user.get("buff_damage_mult"):
        import time
        if user["buff_expires_ts"] > int(time.time()):
            stats["damage"] *= user["buff_damage_mult"]

    return stats


def get_equipped_special_effects(mutations):
    """Возвращает set всех особых эффектов (poison, puncture и т.д.) от надетых мутаций."""
    specials = set()
    if not mutations:
        return specials
    mut_list = mutations if isinstance(mutations, list) else [{"slot": k, **v} for k, v in mutations.items()]
    for m in mut_list:
        if m.get("equipped") and m.get("variant_key"):
            variant = get_mutation_variant(m["slot"], m["variant_key"])
            if variant and variant.get("special_effect"):
                specials.add(variant["special_effect"])
    return specials


def roll_chest_loot(chest_type, owned_variant_keys):
    """Генерирует лут из сундука (ракушки, камни, и шанс на легендарную мутацию)."""
    chest_data = EVENT_CHESTS.get(chest_type, EVENT_CHESTS["default"])
    loot = {
        "shells": chest_data.get("shells", 0),
        "stones": [],
        "mutation": None
    }
    
    colors = list(STONE_COLORS.keys())
    for _ in range(chest_data.get("stones", 0)):
        color = random.choice(colors)
        loot["stones"].append((color, chest_data.get("stone_lvl", 3)))
        
    if random.random() * 100 <= chest_data.get("mut_chance", 0.0):
        possible_muts = []
        for slot, variants in MUTATION_VARIANTS.items():
            for v in variants:
                if v.get("is_special") and v["key"] not in owned_variant_keys:
                    possible_muts.append({"key": v["key"], "slot": slot, "name": v["name"]})
        if possible_muts:
            loot["mutation"] = random.choice(possible_muts)
            
    return loot


def player_attack(stats, monster_evasion=0, force_crit=False):
    if random.random() * 100 < (PLAYER_MISS_CHANCE + monster_evasion):
        return 0, False, True
    dmg = stats["damage"] * random.uniform(0.9, 1.1)
    is_crit = force_crit or (random.random() * 100 < stats["crit_chance"])
    if is_crit:
        dmg *= stats["crit_damage"] / 100
    return round(dmg), is_crit, False


def monster_attack(monster, stats):
    if random.random() * 100 < stats["evasion"]:
        return 0, True
    dmg = monster["dmg"] * random.uniform(0.85, 1.15)
    return round(dmg), False


def gold_reward(monster, stats, user=None):
    mult = 1 + stats["luck"] / 100
    amount = max(1, round(monster["gold"] * mult))
    return apply_permanent_boost(amount, user)


def apply_permanent_boost(amount, user):
    if user and user.get("permanent_boost"):
        return round(amount * PERMANENT_BOOST_MULT)
    return amount


def apply_idle_regen(user, stats, now):
    if user["cur_hp"] >= stats["max_hp"]:
        return stats["max_hp"]
    last_ts = user["last_hp_regen_ts"] or now
    elapsed_minutes = max(0, (now - last_ts) / 60)
    heal_fraction = min(1.0, elapsed_minutes / 30)
    missing = stats["max_hp"] - user["cur_hp"]
    healed = missing * heal_fraction
    return min(stats["max_hp"], round(user["cur_hp"] + healed))


def defeat_knockback_meters(cur_meters):
    knockback = 1
    return max(1, cur_meters - knockback)


def weighted_sample_without_replacement(items, weights, k):
    pool = list(zip(items, weights))
    result = []
    for _ in range(min(k, len(pool))):
        total = sum(w for _, w in pool)
        if total <= 0:
            break
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


def shop_dna_reward(mutations, upgrades_worth):
    avg_level = 1
    if mutations:
        mut_list = mutations if isinstance(mutations, list) else mutations.values()
        total_lvls = sum(m.get("level", 0) for m in mut_list)
        avg_level = max(1, total_lvls // max(1, len(mut_list)))
    return max(5, round(cost_upgrade_mutation(avg_level) * upgrades_worth))


def mythic_events_unlocked(user):
    return (
        user["molts"] >= MYTHIC_EVENT_UNLOCK_MOLTS
        or user["max_meters"] >= MYTHIC_EVENT_UNLOCK_MAX_METERS
        or user["kills"] >= MYTHIC_EVENT_UNLOCK_KILLS
    )


def format_number(num: int) -> str:
    if num < 0:
        return str(num)
    if num >= 1_000_000_000_000_000:
        formatted = f"{num / 1_000_000_000_000_000:.1f}кв"
        return formatted.replace(".0кв", "кв")
    elif num >= 1_000_000_000_000:
        formatted = f"{num / 1_000_000_000_000:.1f}т"
        return formatted.replace(".0т", "т")
    elif num >= 1_000_000_000:
        formatted = f"{num / 1_000_000_000:.1f}б"
        return formatted.replace(".0б", "б")
    elif num >= 1_000_000:
        formatted = f"{num / 1_000_000:.1f}м"
        return formatted.replace(".0м", "м")
    elif num >= 1_000:
        formatted = f"{num / 1_000:.1f}к"
        return formatted.replace(".0к", "к")
    return str(num)


def cost_new_mutation(owned_count):
    base_cost = 25
    return base_cost + (owned_count * 35)

def cost_upgrade_mutation(current_level):
    return max(10, round(15 * (current_level ** 1.4)))
