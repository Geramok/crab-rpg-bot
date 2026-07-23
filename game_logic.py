# -*- coding: utf-8 -*-
"""
Все формулы баланса собраны здесь. Это стартовые цифры для долгой прогрессии —
если тестами выяснится, что где-то слишком легко/тяжело, правь только этот файл.
"""
import math
import random

from data import CRABS, MUTATION_SLOTS, STONE_COLORS, STONE_LEVEL_BONUS, STONE_LEVEL_CHANCE

MOLT_REQUIRED_LEVEL = 70  # уровень краба, при котором доступна линька


def level_up_cost(current_level, molts):
    """Цена повышения уровня краба с current_level на current_level+1.
    Растёт с уровнем и дополнительно масштабируется числом уже пройденных линек,
    чтобы после линьки нельзя было сразу 'на халяву' докупить полвека уровней."""
    base = 6 * (current_level ** 1.35)
    molt_scale = 1 + molts * 0.4
    return max(5, round(base * molt_scale))


def dna_points_for_molt(molts):
    """Сколько очков ДНК даёт очередная линька (растёт медленно, т.к. цены на
    мутации тоже растут — см. mutation_cost)."""
    return 10 + molts * 4


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


def is_boss_meter(meters):
    """Пока не используется отдельно — обычные монстры на охоте, боссы идут через ивенты."""
    return False


def roll_dig_loot():
    """Возвращает список (color, level) добытых камней за одно копание."""
    n = random.randint(3, 6)  # DIG_STONES_MIN/MAX задают общий разброс, конкретика тут
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


def get_effective_stats(user, mutations, stones):
    crab_base = CRABS[user["crab_type"]]
    damage = float(crab_base["damage"])
    evasion = float(crab_base["evasion"])
    luck = float(crab_base["luck"])
    crit_chance = float(crab_base["crit_chance"])
    crit_damage = float(crab_base["crit_damage"])
    max_hp = float(crab_base["max_hp"])

    # рост характеристик от уровня краба (сбрасывается линькой вместе с уровнем)
    damage += user["crab_level"] * 1.4
    max_hp += user["crab_level"] * 4.5

    # бонусы от надетых мутаций (не сбрасываются линькой)
    for slot, m in mutations.items():
        if m and m.get("equipped") and m.get("level", 0) > 0:
            effect = MUTATION_SLOTS[slot]["effect"]
            bonus = MUTATION_SLOTS[slot]["per_level"] * m["level"]
            if effect == "evasion":
                evasion += bonus
            elif effect == "max_hp":
                max_hp += bonus
            elif effect == "damage":
                damage += bonus

    # бонусы от добытых камней (постоянные, не сбрасываются никогда)
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


def player_attack(stats):
    """Считает урон одного тапа по кнопке 'Атака'. Возвращает (урон, был_ли_крит)."""
    dmg = stats["damage"] * random.uniform(0.9, 1.1)
    is_crit = random.random() * 100 < stats["crit_chance"]
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
