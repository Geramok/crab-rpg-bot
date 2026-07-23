# -*- coding: utf-8 -*-
"""
Все формулы баланса собраны здесь. Это стартовые цифры для долгой прогрессии —
если тестами выяснится, что где-то слишком легко/тяжело, правь только этот файл.
"""
import random

from data import CRABS, MUTATION_SLOTS, STONE_COLORS, STONE_LEVEL_BONUS, STONE_LEVEL_CHANCE

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
    """Сколько очков ДНК даёт линька. База растёт с числом линек, а дополнительный
    бонус начисляется за каждый уровень СВЕРХ минимально требуемого — специально,
    чтобы имело смысл забираться выше требуемого уровня, а не линять впритык."""
    required = molt_required_level(molts)
    base = 10 + molts * 5
    over_levels = max(0, crab_level - required)
    bonus = round(over_levels * 0.4)
    return base + bonus


def mutation_cost(slot, target_level, total_levels_owned):
    """Цена повышения мутации slot до уровня target_level.
    total_levels_owned — суммарный уровень ВСЕХ мутаций игрока (до этой покупки),
    из-за чего каждая следующая покупка/апгрейд дороже предыдущей."""
    base = MUTATION_SLOTS[slot]["base_cost"]
    cost = base * (target_level ** 1.6) * (1 + total_levels_owned * 0.22)
    return max(1, round(cost))


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


def get_effective_stats(user, stones):
    """Характеристики краба: базовые от вида краба + уровень + добытые камни.
    Обычные мутации (ноги/панцирь/клешни) СЮДА не входят — это не прибавка к
    характеристикам, а отдельные пассивные способности, см. get_mutation_abilities()."""
    crab_base = CRABS[user["crab_type"]]
    damage = float(crab_base["damage"])
    evasion = float(crab_base["evasion"])
    luck = float(crab_base["luck"])
    crit_chance = float(crab_base["crit_chance"])
    crit_damage = float(crab_base["crit_damage"])
    max_hp = float(crab_base["max_hp"])

    damage += user["crab_level"] * 1.4
    max_hp += user["crab_level"] * 4.5

    for st in stones:
        effect = STONE_COLORS[st["color"]]["effect"]
        bonus = STONE_LEVEL_BONUS[st["level"]] * st["count"]
        if effect == "damage":
            damage += bonus
        elif effect == "evasion":
            evasion += bonus
        elif effect == "luck":
            luck += bonus
        elif effect == "crit_chance":
            crit_chance += bonus
        elif effect == "crit_damage":
            crit_damage += bonus

    evasion = min(evasion, 75.0)
    crit_chance = min(crit_chance, 90.0)

    return {
        "damage": damage,
        "evasion": evasion,
        "luck": luck,
        "crit_chance": crit_chance,
        "crit_damage": crit_damage,
        "max_hp": round(max_hp),
    }


def get_mutation_abilities(mutations):
    """Возвращает силу пассивных навыков от НАДЕТЫХ обычных мутаций.
    dash_chance — шанс двойного удара (ноги), regen_percent — % лечения после
    победы (панцирь), rend_chance — шанс бонусного удара клешнёй (клешни)."""
    abilities = {"dash_chance": 0.0, "regen_percent": 0.0, "rend_chance": 0.0}
    key_by_slot = {"legs": "dash_chance", "shell": "regen_percent", "claws": "rend_chance"}
    for slot, m in mutations.items():
        if m and m.get("equipped") and m.get("level", 0) > 0:
            per_level = MUTATION_SLOTS[slot]["per_level"]
            abilities[key_by_slot[slot]] = per_level * m["level"]
    return abilities


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
