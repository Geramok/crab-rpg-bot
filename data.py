# -*- coding: utf-8 -*-
"""
Статические данные игры. Тут собран весь баланс — если что-то не нравится,
меняй цифры здесь, логика в handlers их просто использует.
"""

# ---------- КРАБЫ ----------
CRABS = {
    1: {
        "name": "🦀 Панцирник",
        "desc": "Сильный, но медленный. Высокий урон и HP, но чаще промахивается по уклонению.",
        "damage": 12, "evasion": 5, "luck": 5, "crit_chance": 5, "crit_damage": 130, "max_hp": 140,
    },
    2: {
        "name": "🦞 Быстроход",
        "desc": "Быстрый краб со средним уроном, хорошее уклонение.",
        "damage": 8, "evasion": 15, "luck": 8, "crit_chance": 10, "crit_damage": 140, "max_hp": 100,
    },
    3: {
        "name": "🦐 Крит-краб",
        "desc": "Средняя скорость, слабый обычный урон, зато частые и мощные криты.",
        "damage": 6, "evasion": 8, "luck": 10, "crit_chance": 25, "crit_damage": 180, "max_hp": 90,
    },
}

# ---------- ЗОНЫ ГЛУБИНЫ (заменяют выбор берега) ----------
DEPTH_ZONES = [
    (0, "🏖️ Берег"),
    (50, "🌊 Мелководье"),
    (200, "🪸 Риф"),
    (500, "🌑 Сумеречная зона"),
    (1000, "🌀 Бездна"),
    (2500, "🎇️ Адские глубины"),
    (5000, "👑 Тронный зал древних"),
]

# ---------- СТЕНЫ ПРОКАЧКИ (барьеры глубины) ----------
DEPTH_BARRIERS = [
    (180, 3),    # перед Рифом
    (480, 6),    # перед Сумеречной зоной
    (950, 10),   # перед Бездной
    (2400, 15),  # перед Адскими глубинами
    (4800, 22),  # перед Тронным залом древних
]

MOLT_RANKS = [
    (0, "🥚️ Личинка"),
    (1, "🐛️ Малёк"),
    (3, "🦀 Молодой краб"),
    (5, "🛡️ Зрелый краб"),
    (8, "👑 Краб-ветеран"),
    (12, "🌊 Легенда глубин"),
]

PLAYER_MISS_CHANCE = 4  

# ---------- МОРСКИЕ СУЩЕСТВА (39 видов) ----------
MONSTERS = [
    # ===== 🏖️ БЕРЕГ (0-90м) =====
    {"key": "hermit_crab", "name": "🐚 Краб-отшельник", "min_meters": 0, "max_meters": 90,
     "hp_mult": 1.0, "dmg_mult": 0.8, "gold_mult": 1.0, "evasion": 5, "weight": 10,
     "art": " .-'-.\n( o.o )\n '-\"-' "},
    {"key": "sand_worm", "name": "🪱 Песчаный червь", "min_meters": 0, "max_meters": 80,
     "hp_mult": 0.7, "dmg_mult": 1.0, "gold_mult": 0.9, "evasion": 8, "weight": 10,
     "art": "~~~o~~~o~~~"},
    {"key": "shore_shrimp", "name": "🦐 Прибрежная креветка", "min_meters": 0, "max_meters": 70,
     "hp_mult": 0.6, "dmg_mult": 0.6, "gold_mult": 0.8, "evasion": 15, "weight": 10,
     "art": "  ..--..\n ( o  o )\n  '.__.' "},
    {"key": "tide_fish", "name": "🐟 Рыбка приливных луж", "min_meters": 0, "max_meters": 100,
     "hp_mult": 0.8, "dmg_mult": 0.7, "gold_mult": 0.9, "evasion": 10, "weight": 10,
     "art": " o==(o)==o "},
    {"key": "barnacle_biter", "name": "🪨 Морской желудь-кусака", "min_meters": 10, "max_meters": 120,
     "hp_mult": 1.6, "dmg_mult": 0.5, "gold_mult": 1.0, "evasion": 3, "weight": 10,
     "art": " .-^^^-.\n( * * * )\n '-...-' "},
    {"key": "seagull", "name": "🐦 Чайка-разорительница", "min_meters": 0, "max_meters": 60,
     "hp_mult": 1.3, "dmg_mult": 1.5, "gold_mult": 1.6, "evasion": 20, "weight": 2,
     "art": "  ^-^-^\n ( o.o )\n  \" \" \" "},

    # ===== 🌊 МЕЛКОВОДЬЕ (~50-280м) =====
    {"key": "mackerel_shoal", "name": "🐟 Стая макрели", "min_meters": 50, "max_meters": 250,
     "hp_mult": 0.7, "dmg_mult": 1.0, "gold_mult": 1.0, "evasion": 12, "weight": 10,
     "art": "o=))) o=))) o=)))"},
    {"key": "grumpy_snail", "name": "🐌 Морская улитка-ворчунья", "min_meters": 60, "max_meters": 220,
     "hp_mult": 1.4, "dmg_mult": 0.4, "gold_mult": 0.9, "evasion": 4, "weight": 10,
     "art": " .--.\n(o o)_/\n '----' "},
    {"key": "reef_octopus", "name": "🐙 Малый осьминог", "min_meters": 40, "max_meters": 230,
     "hp_mult": 0.9, "dmg_mult": 0.9, "gold_mult": 1.1, "evasion": 18, "weight": 10,
     "art": " (o o)\n((   ))\n / | \\ "},
    {"key": "spider_crab", "name": "🕷️ Краб-паук", "min_meters": 80, "max_meters": 280,
     "hp_mult": 1.1, "dmg_mult": 1.2, "gold_mult": 1.1, "evasion": 8, "weight": 10,
     "art": "\\|/ \\|/\n-( * )-\n/|\\ /|\\"},
    {"key": "moon_jelly", "name": "🌕 Лунная медуза", "min_meters": 50, "max_meters": 260,
     "hp_mult": 0.8, "dmg_mult": 0.7, "gold_mult": 1.0, "evasion": 22, "weight": 10,
     "art": "  .--.\n (    )\n  \\||/ "},
    {"key": "king_crab", "name": "👑 Королевский краб-мародёр", "min_meters": 100, "max_meters": 220,
     "hp_mult": 1.8, "dmg_mult": 1.6, "gold_mult": 1.8, "evasion": 6, "weight": 2,
     "art": " (\\=/)\n ( o,o )\n /(   )\\ "},

    # ===== 🪸 РИФ (~200-550м) =====
    {"key": "clownfish_swarm", "name": "🐠 Стая рыб-клоунов", "min_meters": 200, "max_meters": 450,
     "hp_mult": 0.6, "dmg_mult": 1.1, "gold_mult": 1.0, "evasion": 14, "weight": 10,
     "art": "o=))) o=))) o=)))"},
    {"key": "moray_eel", "name": "🐍 Мурена-засадница", "min_meters": 220, "max_meters": 550,
     "hp_mult": 1.0, "dmg_mult": 1.4, "gold_mult": 1.2, "evasion": 10, "weight": 10,
     "art": "~~~~o)))~~~~"},
    {"key": "old_turtle", "name": "🐢 Старая морская черепаха", "min_meters": 250, "max_meters": 600,
     "hp_mult": 2.2, "dmg_mult": 0.6, "gold_mult": 1.3, "evasion": 3, "weight": 10,
     "art": "  .--.\n /(oo)\\\n '-\"\"-' "},
    {"key": "coral_crab", "name": "🦀 Коралловый краб", "min_meters": 200, "max_meters": 480,
     "hp_mult": 1.3, "dmg_mult": 1.0, "gold_mult": 1.1, "evasion": 6, "weight": 10,
     "art": " (\\_/)\n ( .,. )\n /|_|\\ "},
    {"key": "spiky_lionfish", "name": "🦁 Колючая рыба-лев", "min_meters": 260, "max_meters": 520,
     "hp_mult": 0.7, "dmg_mult": 1.8, "gold_mult": 1.2, "evasion": 8, "weight": 10,
     "art": " *\\|/*\n*-(o)-*\n *//|\\\\* "},
    {"key": "octopus_patriarch", "name": "🐙 Осьминог-патриарх рифа", "min_meters": 300, "max_meters": 500,
     "hp_mult": 2.0, "dmg_mult": 1.5, "gold_mult": 1.8, "evasion": 18, "weight": 2,
     "art": "  (o   o)\n ((     ))\n  \\/ | \\/ "},

    # ===== 🌑 СУМЕРЕЧНАЯ ЗОНА (~500-1100м) =====
    {"key": "anglerfish", "name": "🏮 Рыба-удильщик", "min_meters": 500, "max_meters": 1000,
     "hp_mult": 1.0, "dmg_mult": 1.3, "gold_mult": 1.3, "evasion": 10, "weight": 10,
     "art": " o~*\n( o )\n '-' "},
    {"key": "vampire_squid", "name": "🦇 Кальмар-вампир", "min_meters": 550, "max_meters": 1050,
     "hp_mult": 0.9, "dmg_mult": 1.5, "gold_mult": 1.3, "evasion": 16, "weight": 10,
     "art": " (@ @)\n :|||:\n  \\_/ "},
    {"key": "gulper_eel", "name": "🐍 Большерот-угорь", "min_meters": 600, "max_meters": 1100,
     "hp_mult": 0.8, "dmg_mult": 1.6, "gold_mult": 1.2, "evasion": 12, "weight": 10,
     "art": " o====)))\n  \\___/ "},
    {"key": "ghost_jelly", "name": "🎐 Медуза-призрак глубин", "min_meters": 500, "max_meters": 950,
     "hp_mult": 0.7, "dmg_mult": 1.0, "gold_mult": 1.1, "evasion": 25, "weight": 10,
     "art": "  .-.\n (   )\n  )||( "},
    {"key": "hatchet_fish", "name": "🔪 Рыба-топорик", "min_meters": 520, "max_meters": 1000,
     "hp_mult": 0.9, "dmg_mult": 1.2, "gold_mult": 1.15, "evasion": 14, "weight": 10,
     "art": " /\\_/\\\n( o o )\n \\/ \\/ "},
    {"key": "abyss_empress", "name": "👑 Светящаяся владычица тьмы", "min_meters": 600, "max_meters": 950,
     "hp_mult": 1.8, "dmg_mult": 1.7, "gold_mult": 1.9, "evasion": 20, "weight": 2,
     "art": "  *   *\n ( o.o )\n  \\_-_/ "},

    # ===== 🌀 БЕЗДНА (~1000-2400м) =====
    {"key": "giant_isopod", "name": "🪳 Гигантский изопод", "min_meters": 1000, "max_meters": 2000,
     "hp_mult": 1.9, "dmg_mult": 0.8, "gold_mult": 1.3, "evasion": 4, "weight": 10,
     "art": " (=====)\n ( o o )\n '-----' "},
    {"key": "black_dragonfish", "name": "🐉 Чёрная рыба-дракон", "min_meters": 1050, "max_meters": 2200,
     "hp_mult": 1.1, "dmg_mult": 1.7, "gold_mult": 1.4, "evasion": 12, "weight": 10,
     "art": " o===))))\n  \\___/ "},
    {"key": "scavenger_shrimp", "name": "🦐 Донный падальщик", "min_meters": 1000, "max_meters": 1900,
     "hp_mult": 0.8, "dmg_mult": 1.1, "gold_mult": 1.2, "evasion": 10, "weight": 10,
     "art": "  .--.\n ()  ()\n  '--' "},
    {"key": "giant_squid", "name": "🦑 Гигантский кальмар", "min_meters": 1200, "max_meters": 2500,
     "hp_mult": 1.6, "dmg_mult": 1.5, "gold_mult": 1.6, "evasion": 14, "weight": 10,
     "art": " (@ @)\n /|||\\\n  | | "},
    {"key": "abyss_worm", "name": "🪱 Бездонный червь", "min_meters": 1100, "max_meters": 2300,
     "hp_mult": 1.3, "dmg_mult": 1.3, "gold_mult": 1.3, "evasion": 6, "weight": 10,
     "art": "==o==o==o=="},
    {"key": "colossal_squid", "name": "🦑 Колоссальный кальмар-владыка", "min_meters": 1400, "max_meters": 2300,
     "hp_mult": 2.4, "dmg_mult": 2.0, "gold_mult": 2.2, "evasion": 16, "weight": 2,
     "art": "  (@   @)\n //|||||\\\\\n  |     | "},

    # ===== 🎇 АДСКИЕ ГЛУБИНЫ (~2500-4800м) =====
    {"key": "lava_worm", "name": "🌋 Огненный червь бездны", "min_meters": 2500, "max_meters": 4000,
     "hp_mult": 1.4, "dmg_mult": 1.9, "gold_mult": 1.5, "evasion": 6, "weight": 10,
     "art": "*=*=*=*=*"},
    {"key": "hell_eel", "name": "🔥 Адский угорь", "min_meters": 2600, "max_meters": 4500,
     "hp_mult": 1.2, "dmg_mult": 2.0, "gold_mult": 1.5, "evasion": 14, "weight": 10,
     "art": " *===)))*\n  \\___/ "},
    {"key": "bone_reaper_crab", "name": "☠️ Костяной краб-жнец", "min_meters": 2500, "max_meters": 4200,
     "hp_mult": 2.0, "dmg_mult": 1.6, "gold_mult": 1.6, "evasion": 5, "weight": 10,
     "art": " (x_x)\n /|_|\\\n  ' ' "},
    {"key": "shadow_ray", "name": "🌑 Скат-тень", "min_meters": 2700, "max_meters": 5000,
     "hp_mult": 1.0, "dmg_mult": 1.8, "gold_mult": 1.5, "evasion": 22, "weight": 10,
     "art": " __/\\__\n( . . )\n \\/  \\/ "},
    {"key": "abyss_serpent", "name": "🐉 Змей пылающей бездны", "min_meters": 3000, "max_meters": 4700,
     "hp_mult": 2.6, "dmg_mult": 2.2, "gold_mult": 2.3, "evasion": 15, "weight": 2,
     "art": " *~*~*~*\n( O   O )\n *~*~*~* "},

    # ===== 👑 ТРОННЫЙ ЗАЛ ДРЕВНИХ (5000м+, дна нет) =====
    {"key": "ancient_blind_fish", "name": "👁️ Древняя слепая рыба", "min_meters": 5000,
     "hp_mult": 1.5, "dmg_mult": 1.7, "gold_mult": 1.8, "evasion": 8, "weight": 10,
     "art": " .-o-.\n(  x  )\n '-o-' "},
    {"key": "throne_guard_crab", "name": "🦀 Краб-страж трона", "min_meters": 5000,
     "hp_mult": 2.5, "dmg_mult": 1.8, "gold_mult": 2.0, "evasion": 6, "weight": 10,
     "art": " (\\=Y=/)\n ( o,o )\n /(   )\\ "},
    {"key": "eldritch_squid", "name": "🐙 Кальмар из бездны времён", "min_meters": 5000,
     "hp_mult": 1.8, "dmg_mult": 2.0, "gold_mult": 2.0, "evasion": 18, "weight": 10,
     "art": " (0   0)\n //|||\\\\\n  |   | "},
    {"key": "abyssal_empress_jelly", "name": "👑 Медуза-императрица бездны", "min_meters": 5000,
     "hp_mult": 1.6, "dmg_mult": 1.5, "gold_mult": 2.0, "evasion": 20, "weight": 10,
     "art": "  .===.\n ( o o )\n  )|||( "},
    {"key": "time_lost_shark", "name": "🦈 Акула из-за грани времён", "min_meters": 5000,
     "hp_mult": 1.9, "dmg_mult": 2.1, "gold_mult": 1.9, "evasion": 10, "weight": 10,
     "art": " ,-^^-.\n( o.o ))=\n '--v--' "},
    {"key": "obsidian_colossus_crab", "name": "🦀 Обсидиановый краб-колосс", "min_meters": 5000,
     "hp_mult": 2.8, "dmg_mult": 1.9, "gold_mult": 2.1, "evasion": 4, "weight": 10,
     "art": " (\\===/)\n ( O,O )\n /(   )\\ "},
    {"key": "whispering_eel", "name": "🐍 Шепчущий угорь глубин", "min_meters": 5000,
     "hp_mult": 1.3, "dmg_mult": 1.6, "gold_mult": 1.7, "evasion": 24, "weight": 10,
     "art": "===o)))===o)))"},
    {"key": "forgotten_king_fish", "name": "👑 Рыба забытого короля", "min_meters": 5000,
     "hp_mult": 2.0, "dmg_mult": 1.8, "gold_mult": 2.2, "evasion": 9, "weight": 10,
     "art": "  .=^=.\n ( o o )\n  \\===/ "},
    {"key": "ancient_guardian", "name": "👑 Хранитель Трона Древних", "min_meters": 5000,
     "hp_mult": 3.0, "dmg_mult": 2.5, "gold_mult": 2.8, "evasion": 12, "weight": 2,
     "art": "  .=====.\n ( O   O )\n  '=====' "},
]

GUARD_CAMP_INTERVAL = 100
GUARD_CAMP_ELITE_MULT = 1.25
ELITE_ENCOUNTER_INTERVAL = 10
ELITE_ENCOUNTER_MULT = 1.5

SHORES = {1: "🏖️ Песчаный берег", 2: "🪨 Скалистый берег", 3: "🌴 Коралловый берег"}

# ---------- МУТАЦИИ ----------
MUTATION_SLOT_NAMES = {
    "legs": "🐾 Ноги",
    "shell": "🛡️ Панцирь",
    "claws": "✂️ Клешни",
}
MUTATION_SLOT_BASE_COST = {"legs": 5, "shell": 5, "claws": 6}

MUTATION_VARIANTS = {
    "legs": [
        {"key": "stone_leg", "name": "🪨 Каменная нога", "buff_stat": "max_hp", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "evasion", "base_debuff": 2.0, "debuff_per_level": 0.2},
        {"key": "mercury_leg", "name": "🔘 Ртутная нога", "buff_stat": "evasion", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "damage", "base_debuff": 2.0, "debuff_per_level": 0.2},
        {"key": "coral_leg", "name": "🪸 Коралловая нога", "buff_stat": "luck", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "max_hp", "base_debuff": 2.0, "debuff_per_level": 0.2},
        # Легендарные мутации:
        {"key": "puncture_legs", "name": "🗡️ Острые костеходы", "buff_stat": "crit_chance", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "max_hp", "base_debuff": 15.0, "debuff_per_level": 1.0, "special_effect": "puncture", "desc": "10% шанс на гарантированный крит независимо от шанса. Сильно снижает базовую прочность.", "is_special": True},
        {"key": "frenzy_legs", "name": "🌀 Бешеные ходоки", "buff_stat": "damage", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "evasion", "base_debuff": 15.0, "debuff_per_level": 1.0, "special_effect": "frenzy", "desc": "После крита шанс 20% нанести ещё один удар. Краб становится неповоротливым (-уклонение).", "is_special": True},
    ],
    "claws": [
        {"key": "golden_claw", "name": "🪝️ Золотая клешня", "buff_stat": "luck", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "damage", "base_debuff": 2.0, "debuff_per_level": 0.2},
        {"key": "steel_claw", "name": "⚙️ Стальная клешня", "buff_stat": "damage", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "evasion", "base_debuff": 2.0, "debuff_per_level": 0.2},
        {"key": "venom_claw", "name": "🌵️ Шипованная клешня", "buff_stat": "crit_chance", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "max_hp", "base_debuff": 2.0, "debuff_per_level": 0.2},
        # Легендарные мутации:
        {"key": "poison_claws", "name": "🧪 Ядовитая клешня-хлыст", "buff_stat": "crit_damage", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "luck", "base_debuff": 15.0, "debuff_per_level": 1.0, "special_effect": "poison", "desc": "15% шанс отравить врага. Удача покидает тебя.", "is_special": True},
        {"key": "vampire_claws", "name": "🛸️ Инопланетная клешня кровопийцы", "buff_stat": "damage", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "max_hp", "base_debuff": 20.0, "debuff_per_level": 1.5, "special_effect": "vampirism", "desc": "Лечит на 25% от урона (макс. 10% ХП за удар). Критически снижает базовую прочность.", "is_special": True},
    ],
    "shell": [
        {"key": "obsidian_shell", "name": "🌋 Обсидиановый панцирь", "buff_stat": "max_hp", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "luck", "base_debuff": 2.0, "debuff_per_level": 0.2},
        {"key": "pearl_shell", "name": "🦪 Жемчужный панцирь", "buff_stat": "crit_damage", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "evasion", "base_debuff": 2.0, "debuff_per_level": 0.2},
        {"key": "sponge_shell", "name": "🧽 Губчатый панцирь", "buff_stat": "evasion", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "damage", "base_debuff": 2.0, "debuff_per_level": 0.2},
        # Легендарные мутации:
        {"key": "camo_shell", "name": "🌊 Мимикрирующий панцирь", "buff_stat": "evasion", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "damage", "base_debuff": 15.0, "debuff_per_level": 1.0, "special_effect": "camouflage", "desc": "10% шанс избежать удара. Атаки краба становятся очень слабыми.", "is_special": True},
        {"key": "greed_shell", "name": "🏆️ Блестящий золотом панцирь", "buff_stat": "luck", "base_buff": 5.0, "buff_per_level": 0.5, "debuff_stat": "max_hp", "base_debuff": 15.0, "debuff_per_level": 1.0, "special_effect": "greed", "desc": "15% шанс удвоить золото за врага. Панцирь становится очень хрупким.", "is_special": True},
    ],
}

STAT_LABELS = {
    "damage": "урону", "evasion": "уклонению", "luck": "удаче",
    "crit_chance": "крит. шансу", "crit_damage": "крит. урону", "max_hp": "прочности",
}

# ---------- СУНДУКИ ЗА ИВЕНТЫ ----------
EVENT_CHESTS = {
    1: {"name": "⚪ Жемчужный сундук", "shells": 3, "stones": 4, "stone_lvl": 3, "mut_chance": 30.0},
    2: {"name": "🟡 Золотой сундук", "shells": 2, "stones": 3, "stone_lvl": 3, "mut_chance": 25.0},
    3: {"name": "🟣 Роскошный сундук", "shells": 1, "stones": 2, "stone_lvl": 3, "mut_chance": 20.0},
    "default": {"name": "🟤 Старый сундук", "shells": 0, "stones": 1, "stone_lvl": 3, "mut_chance": 0.6},
}

# ---------- АКТИВНЫЕ БОЕВЫЕ СПОСОБНОСТИ ----------
SHIELD_ABILITY = {
    "name": "🛡️ Панцирь", "block_percent": 80, "cooldown_turns": 3,
    "desc": "Блокирует 80% входящего урона в этом ходу. Откат 3 хода.",
}
MARK_ABILITY = {
    "name": "🪝️ Проклятье", "gold_mult": 2, "miss_turns": 2,
    "desc": "Удваивает золото, если добьёшь помеченного врага, но следующие "
            "2 твоих удара гарантированно промахнутся. Раз за бой.",
}

UNIQUE_ABILITIES = {
    1: {  
        "key": "crushing_blow", "name": "🦀 Раздавливающий захват",
        "damage_mult": 2.5, "self_damage_percent": 20,
        "desc": "Мощнейший захват клешнёй (×2.5 урона), но отбирает 20% твоей прочности. Раз за бой.",
    },
    2: {  
        "key": "sprint", "name": "🍃️ Боковой рывок",
        "sprint_turns": 4, "fatigue_turns": 4,
        "fatigue_miss_bonus": 15, "fatigue_evasion_penalty": 15,
        "desc": "Следующие 4 хода — гарантированное попадание и уклонение. "
                "Затем 4 хода усталости: чаще промахи, реже уклонения. Раз за бой.",
    },
    3: {  
        "key": "blood_rage", "name": "🩸 Кровавый раж",
        "self_damage_percent": 6,
        "desc": "До конца боя ВСЕ удары критические, но каждый удар отбирает "
                "6% твоей прочности. Раз за бой.",
    },
}

# ---------- КАМНИ (добываются копанием) ----------
STONE_COLORS = {
    "red": {"name": "🔴 Красный", "effect": "damage"},
    "blue": {"name": "🔵 Синий", "effect": "evasion"},
    "green": {"name": "🟢 Зелёный", "effect": "luck"},
    "cyan": {"name": "🩵 Голубой", "effect": "crit_chance"},
    "orange": {"name": "🟠 Оранжевый", "effect": "crit_damage"},
}
STONE_EFFECT_BONUS = {
    "damage": {1: 3, 2: 5, 3: 7},
    "max_hp": {1: 6, 2: 12, 3: 25},
    "evasion": {1: 0.15, 2: 0.35, 3: 0.7},
    "luck": {1: 0.15, 2: 0.35, 3: 0.7},
    "crit_chance": {1: 0.15, 2: 0.35, 3: 0.7},
    "crit_damage": {1: 0.4, 2: 1.0, 3: 2.0},
}
STONE_LEVEL_CHANCE = {1: 0.55, 2: 0.45, 3: 0.35}
DIG_STONES_PER_HOUR = 0.5
DIG_DURATION_OPTIONS_HOURS = [2, 4, 16, 24]

# ---------- РЕСУРСЫ И КРАФТ ----------
RESOURCES = {
    "shard": {"name": "🐚 Осколок панциря"},
    "essence": {"name": "💧 Морская эссенция"},
    "bone": {"name": "🦴 Кость монстра"},
}
RESOURCE_DROP_CHANCE_KILL = 0.15
RESOURCE_DROP_CHANCE_DIG = 0.5

NECTAR_RECIPE = {"shard": 3, "essence": 2, "bone": 1}
NECTAR_BUFF_DAMAGE_MULT = 1.25
NECTAR_BUFF_DURATION_SECONDS = 20 * 60

# ---------- МАГАЗИН (Telegram Stars) ----------
SHOP_ITEMS = {
    "golden_ray": {
        "title": "🥇 Золотой скат",
        "description": "Щедрая порция золота для быстрой прокачки краба.",
        "stars": 100,
        "reward_type": "gold",
        "levels_worth": 9,
    },
    "blue_shrimp": {
        "title": "🧬 Синяя креветка",
        "description": "Запас очков ДНК для развития мутаций.",
        "stars": 150,
        "reward_type": "dna",
        "mutation_upgrades_worth": 4,
    },
    "eternal_tide": {
        "title": "🌟 Вечный прилив",
        "description": "Разовая покупка — НАВСЕГДА +15% к золоту и очкам ДНК со всех источников.",
        "stars": 400,
        "reward_type": "permanent_boost",
    },
}

PERMANENT_BOOST_MULT = 1.15

# ---------- МИФИЧЕСКИЕ ИВЕНТЫ ----------
MYTHIC_EVENT_UNLOCK_MOLTS = 2
MYTHIC_EVENT_UNLOCK_MAX_METERS = 300
MYTHIC_EVENT_UNLOCK_KILLS = 450

MYTHIC_EVENTS = [
    {"name": "🐙 Тенеморф Бездны",
     "description": "Из самой глубокой впадины поднялась тварь без формы — она меняет очертания и питается страхом.",
     "art": "  (o   o)\n ((     ))\n  \\/ | \\/ ",
     "hp_flavor": "🫀 Тёмная материя клубится, поглощая твои удары..."},
    {"name": "👑 Королева Медуз Абиссаль",
     "description": "Древняя королева медуз пробудилась и парализует всё живое своим ядовитым туманом.",
     "art": "  .===.\n ( o o )\n  )|||( ",
     "hp_flavor": "☠️ Щупальца сочатся ядом, отражая атаки..."},
]

# ---------- ТЕКСТЫ И ПРОМОКОДЫ ----------
INTRO_TEXT = "🦀 Добро пожаловать в игру! Исследуй глубины, сражайся с монстрами и эволюционируй."
HELP_PAGES = [
    ("Основы игры", "Отправляйся на охоту, копи золото и ДНК, чтобы стать самым сильным крабом на дне океана!"),
    ("Мутации", "Покупай мутации за ДНК в лаборатории. Они дают процентные бонусы к характеристикам.")
]
PROMO_CODES = {
    "стример2026": {"gold": 1000, "dna": 50, "shells": 5}
}
