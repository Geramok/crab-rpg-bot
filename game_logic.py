# -*- coding: utf-8 -*-
"""
Все формулы баланса собраны здесь. Это стартовые цифры для долгой прогрессии —
если тестами выяснится, что где-то слишком легко/тяжело, правь только этот файл.
"""
import random

from data import (
    CRABS, MUTATION_SLOT_BASE_COST, MUTATION_VARIANTS,
    STONE_COLORS, STONE_LEVEL_BONUS, STONE_LEVEL_CHANCE,
    MYTHIC_EVENT_UNLOCK_MOLTS, MYTHIC_EVENT_UNLOCK_MAX_METERS, MYTHIC_EVENT_UNLOCK_KILLS,
)

MOLT_BASE_LEVEL = 70          # уровень, нужный для 1-й линьки
MOLT_LEVEL_STEP = 15          # на сколько растёт требование с каждой следующей линькой


def molt_required_level(molts):
    """Уровень краба, необходимый для (molts+1)-й линьки.
    Каждая следующая линька требует ощутимо более высокого уровня — специально,
    чтобы нельзя было бесконечно линять на минимальном уровне."""
    return MOLT_BASE_LEVEL + molts * MOLT_LEVEL_STEP


def level_up_cost(current_level, molts):
    """Цена повышения уровня краба с current_level на current_level+1."""
    base = 6 * (current_level ** 1.35)
    molt_scale = 1 + molts * 0.4
    return max(5, round(base * molt_scale))


def dna_points_for_molt(molts, crab_level):
    """Сколько очков ДНК даёт линька. База растёт ЭКСПОНЕНЦИАЛЬНО вместе с
    числом линек (чтобы поспевать за тем, как дорожают мутации — см.
    mutation_cost), а дополнительный бонус начисляется за каждый уровень
    СВЕРХ минимально требуемого — специально, чтобы имело смысл забираться
    выше требуемого уровня, а не линять впритык."""
    required = molt_required_level(molts)
    base = 14 * (1.45 ** molts)
    over_levels = max(0, crab_level - required)
    bonus = over_levels * 1.0
    return round(base + bonus)


def mutation_cost(slot, target_level, total_levels_owned):
    """Цена повышения мутации slot до уровня target_level (первая покупка = выпадение
    случайного артефакта, дальнейшие = его прокачка).
    total_levels_owned — суммарный уровень ВСЕХ мутаций игрока (до этой покупки),
    из-за чего каждая следующая покупка/апгрейд дороже предыдущей."""
    base = MUTATION_SLOT_BASE_COST[slot]
    cost = base * (target_level ** 1.35) * (1 + total_levels_owned * 0.10)
    return max(1, round(cost))


def roll_mutation_variant(slot):
    """Случайно выбирает артефакт для слота при первой покупке мутации."""
    return random.choice(MUTATION_VARIANTS[slot])


def get_mutation_variant(slot, variant_key):
    for v in MUTATION_VARIANTS[slot]:
        if v["key"] == variant_key:
            return v
    return None


def next_monster_meters(current_meters):
    step = random.randint(1, 15)
    return current_meters + step


def monster_stats(meters):
    """HP/урон/золото монстра в зависимости от того, на каком метре он встретился."""
    hp = int(12 + meters * 2.6 + meters ** 1.12)
    dmg = int(2 + meters * 0.55 + (meters ** 1.05) * 0.08)
    gold = int(5 + meters * 1.5 + (meters ** 1.08) * 0.25)
    return {"hp": hp, "max_hp": hp, "dmg": max(1, dmg), "gold": max(1, gold)}


def roll_dig_loot():
    """Возвращает список (color, level) добытых камней за одно копание."""
    n = random.randint(3, 6)
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


def get_effective_stats(user, stones, mutations=None):
    """Характеристики краба: базовые от вида краба + уровень + камни + надетые
    мутации-артефакты (у каждой — один плюс и один минус к характеристике)."""
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
        bonus = STONE_LEVEL_BONUS[st["level"]] * st["count"]
        stats[effect] += bonus

    if mutations:
        for slot, m in mutations.items():
            if not (m and m.get("equipped") and m.get("level", 0) > 0 and m.get("variant_key")):
                continue
            variant = get_mutation_variant(slot, m["variant_key"])
            if not variant:
                continue
            level = m["level"]
            stats[variant["buff_stat"]] += variant["buff_per_level"] * level
            stats[variant["debuff_stat"]] -= variant["debuff_per_level"] * level

    stats["evasion"] = max(0.0, min(stats["evasion"], 75.0))
    stats["crit_chance"] = max(0.0, min(stats["crit_chance"], 90.0))
    stats["damage"] = max(1.0, stats["damage"])
    stats["max_hp"] = max(10, round(stats["max_hp"]))

    return stats


def player_attack(stats, force_crit=False):
    """Считает урон одного тапа по кнопке 'Атака'. Возвращает (урон, был_ли_крит)."""
    dmg = stats["damage"] * random.uniform(0.9, 1.1)
    is_crit = force_crit or (random.random() * 100 < stats["crit_chance"])
    if is_crit:
        dmg *= stats["crit_damage"] / 100
    return round(dmg), is_crit


def monster_attack(monster, stats):
    """Считает, попал ли монстр по крабу и на сколько. Возвращает (урон, уклонился_ли)."""
    if random.random() * 100 < stats["evasion"]:
        return 0, True
    dmg = monster["dmg"] * random.uniform(0.85, 1.15)
    return round(dmg), False


def gold_reward(monster, stats):
    mult = 1 + stats["luck"] / 100
    return max(1, round(monster["gold"] * mult))


def weighted_sample_without_replacement(items, weights, k):
    """Взвешенная выборка БЕЗ повторов — используется для честной раздачи
    жемчужных кейсов на ивентах (не только топовым игрокам по урону)."""
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


# ---------------- Магазин: награда в процентах от текущего прогресса ----------------

def shop_gold_reward(user, levels_worth):
    """Золото = стоимость levels_worth уровней прокачки НА ТЕКУЩЕМ этапе игры.
    Так покупка одинаково полезна и в начале, и на 100-м уровне, и её нельзя
    абузить, скупая дёшево на старте — ранняя стоимость уровня сама по себе мала."""
    cost = level_up_cost(user["crab_level"], user["molts"])
    return max(50, round(cost * levels_worth))


def shop_dna_reward(mutations, upgrades_worth):
    """Очки ДНК = средняя стоимость upgrades_worth апгрейдов мутаций на текущем
    этапе (учитывает суммарный уровень уже купленных мутаций)."""
    total_levels = sum(m.get("level", 0) for m in mutations.values()) if mutations else 0
    costs = []
    for slot in MUTATION_SLOT_BASE_COST:
        cur_level = mutations.get(slot, {}).get("level", 0) if mutations else 0
        costs.append(mutation_cost(slot, cur_level + 1, total_levels))
    avg_cost = sum(costs) / len(costs)
    return max(5, round(avg_cost * upgrades_worth))


# ---------------- Открытие мифических ивентов ----------------

def mythic_events_unlocked(user):
    """Несколько альтернативных путей открытия ивентов — не только линьки,
    но и большой пройденный путь или много убийств, чтобы не запирать контент
    только за самым медленным способом прогрессии."""
    return (
        user["molts"] >= MYTHIC_EVENT_UNLOCK_MOLTS
        or user["max_meters"] >= MYTHIC_EVENT_UNLOCK_MAX_METERS
        or user["kills"] >= MYTHIC_EVENT_UNLOCK_KILLS
    )
