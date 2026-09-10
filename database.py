# -*- coding: utf-8 -*-
import asyncio
import os
import sqlite3
import time
from contextlib import closing

from config import DB_PATH

_wal_enabled = False

async def run_async(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)

_db_dir = os.path.dirname(DB_PATH)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    global _wal_enabled
    if not _wal_enabled:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        _wal_enabled = True
    else:
        conn.execute("PRAGMA busy_timeout=10000")
    return conn

def _safe_migrate(conn, sql):
    try:
        conn.execute(sql)
    except sqlite3.OperationalError:
        pass 

def init_db():
    with closing(get_conn()) as conn, conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, nickname TEXT, crab_type INTEGER,
            shore INTEGER, crab_level INTEGER DEFAULT 1, gold INTEGER DEFAULT 0,
            dna_points INTEGER DEFAULT 0, molts INTEGER DEFAULT 0, max_meters INTEGER DEFAULT 0,
            cur_meters INTEGER DEFAULT 0, cur_hp INTEGER DEFAULT 0, in_hunt INTEGER DEFAULT 0,
            monster_json TEXT, kills INTEGER DEFAULT 0, boss_kills INTEGER DEFAULT 0,
            dig_start_ts INTEGER, dig_duration_seconds INTEGER, last_hp_regen_ts INTEGER,
            last_nick_change_ts INTEGER, registered_at INTEGER, total_earned_gold INTEGER DEFAULT 0,
            total_dna_earned INTEGER DEFAULT 0, nautilus_shells INTEGER DEFAULT 0,
            buff_damage_mult REAL, buff_expires_ts INTEGER, permanent_boost INTEGER DEFAULT 0,
            battle_message_id INTEGER, boss_cooldown_ts INTEGER DEFAULT 0
        )
        """)
        for col, coltype in [
            ("dig_duration_seconds", "INTEGER"), ("last_hp_regen_ts", "INTEGER"),
            ("buff_damage_mult", "REAL"), ("buff_expires_ts", "INTEGER"),
            ("permanent_boost", "INTEGER DEFAULT 0"), ("battle_message_id", "INTEGER"),
            ("boss_cooldown_ts", "INTEGER DEFAULT 0"),
        ]:
            _safe_migrate(conn, f"ALTER TABLE users ADD COLUMN {col} {coltype}")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS stones (
            user_id INTEGER, color TEXT, level INTEGER, count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, color, level)
        )
        """)
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS mutations (
            user_id INTEGER, slot TEXT, level INTEGER DEFAULT 0,
            equipped INTEGER DEFAULT 0, variant_key TEXT,
            PRIMARY KEY (user_id, slot)
        )
        """)
        _safe_migrate(conn, "ALTER TABLE mutations ADD COLUMN variant_key TEXT")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS mutations_v2 (
            user_id INTEGER, variant_key TEXT, slot TEXT, level INTEGER DEFAULT 1,
            equipped INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, variant_key)
        )
        """)
        try:
            conn.execute("""
            INSERT OR IGNORE INTO mutations_v2 (user_id, variant_key, slot, level, equipped)
            SELECT user_id, variant_key, slot, level, equipped FROM mutations WHERE variant_key IS NOT NULL
            """)
        except Exception:
            pass

        conn.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            user_id INTEGER, key TEXT, count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, key)
        )
        """)
        
        # НОВАЯ ТАБЛИЦА ДЛЯ СУНДУКОВ
        conn.execute("""
        CREATE TABLE IF NOT EXISTS chests (
            user_id INTEGER, chest_type TEXT, count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, chest_type)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT,
            started_at INTEGER, ends_at INTEGER, active INTEGER DEFAULT 1
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS event_damage (
            event_id INTEGER, user_id INTEGER, damage INTEGER DEFAULT 0,
            PRIMARY KEY (event_id, user_id)
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS promo_redemptions (
            user_id INTEGER, code TEXT, redeemed_at INTEGER,
            PRIMARY KEY (user_id, code)
        )
        """)

# ---------------- USERS ----------------
def get_user(user_id):
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None

def user_exists(user_id):
    return get_user(user_id) is not None

def create_user(user_id, username):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO users (user_id, username, nickname, registered_at, last_hp_regen_ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, username, username, int(time.time()), int(time.time())),
        )

def update_user(user_id, **fields):
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [user_id]
    with closing(get_conn()) as conn, conn:
        conn.execute(f"UPDATE users SET {keys} WHERE user_id=?", values)

def try_spend(user_id, field, amount):
    with closing(get_conn()) as conn, conn:
        cur = conn.execute(
            f"UPDATE users SET {field} = {field} - ? WHERE user_id=? AND {field} >= ?",
            (amount, user_id, amount),
        )
        return cur.rowcount > 0

def try_start_dig(user_id, duration_seconds):
    with closing(get_conn()) as conn, conn:
        cur = conn.execute(
            "UPDATE users SET dig_start_ts=?, dig_duration_seconds=? WHERE user_id=? AND dig_start_ts IS NULL",
            (int(time.time()), duration_seconds, user_id),
        )
        return cur.rowcount > 0

def try_collect_dig(user_id, expected_start_ts):
    with closing(get_conn()) as conn, conn:
        cur = conn.execute(
            "UPDATE users SET dig_start_ts=NULL, dig_duration_seconds=NULL WHERE user_id=? AND dig_start_ts=?",
            (user_id, expected_start_ts),
        )
        return cur.rowcount > 0

def try_start_new_hunt(user_id, monster_json, cur_hp, now):
    with closing(get_conn()) as conn, conn:
        cur = conn.execute(
            "UPDATE users SET in_hunt=1, monster_json=?, cur_hp=?, last_hp_regen_ts=? "
            "WHERE user_id=? AND in_hunt=0",
            (monster_json, cur_hp, now, user_id),
        )
        return cur.rowcount > 0

def try_apply_attack_result(user_id, expected_monster_json, **updates):
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [user_id, expected_monster_json]
    with closing(get_conn()) as conn, conn:
        cur = conn.execute(
            f"UPDATE users SET {set_clause} WHERE user_id=? AND monster_json=? AND in_hunt=1",
            values,
        )
        return cur.rowcount > 0

def get_top_players(limit=10):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT nickname, crab_level, molts, max_meters FROM users ORDER BY molts DESC, crab_level DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

def find_user_by_nickname(nickname):
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE nickname = ? COLLATE NOCASE LIMIT 1", (nickname,)
        ).fetchone()
        return dict(row) if row else None

def get_random_players(exclude_user_id, limit=3):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE user_id != ? ORDER BY RANDOM() LIMIT ?",
            (exclude_user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

# ---------------- STONES ----------------
def add_stone(user_id, color, level, amount=1):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO stones (user_id, color, level, count) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, color, level) DO UPDATE SET count = count + ?",
            (user_id, color, level, amount, amount),
        )

def get_stones(user_id):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT color, level, count FROM stones WHERE user_id=? AND count > 0", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

# ---------------- RESOURCES / КРАФТ ----------------
def add_resource(user_id, key, amount=1):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO resources (user_id, key, count) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET count = count + ?",
            (user_id, key, amount, amount),
        )

def get_resources(user_id):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT key, count FROM resources WHERE user_id=?", (user_id,)
        ).fetchall()
        return {r["key"]: r["count"] for r in rows}

def try_craft(user_id, recipe):
    with closing(get_conn()) as conn, conn:
        current = {
            r["key"]: r["count"]
            for r in conn.execute("SELECT key, count FROM resources WHERE user_id=?", (user_id,)).fetchall()
        }
        for key, need in recipe.items():
            if current.get(key, 0) < need:
                return False
        for key, need in recipe.items():
            conn.execute(
                "UPDATE resources SET count = count - ? WHERE user_id=? AND key=?",
                (need, user_id, key),
            )
        return True

# ---------------- MUTATIONS V2 ----------------
def get_mutations_v2(user_id):
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT * FROM mutations_v2 WHERE user_id=?", (user_id,)).fetchall()
        return [dict(r) for r in rows]

def get_mutation_by_key(user_id, variant_key):
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT * FROM mutations_v2 WHERE user_id=? AND variant_key=?", (user_id, variant_key)).fetchone()
        return dict(row) if row else None

def add_new_mutation(user_id, variant_key, slot):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT OR IGNORE INTO mutations_v2 (user_id, variant_key, slot, level, equipped) VALUES (?, ?, ?, 1, 0)",
            (user_id, variant_key, slot)
        )

def equip_mutation(user_id, variant_key, slot):
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE mutations_v2 SET equipped=0 WHERE user_id=? AND slot=?", (user_id, slot))
        conn.execute("UPDATE mutations_v2 SET equipped=1 WHERE user_id=? AND variant_key=?", (user_id, variant_key))

def unequip_mutation(user_id, variant_key):
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE mutations_v2 SET equipped=0 WHERE user_id=? AND variant_key=?", (user_id, variant_key))

def upgrade_mutation(user_id, variant_key):
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE mutations_v2 SET level = level + 1 WHERE user_id=? AND variant_key=?", (user_id, variant_key))

# ---------------- СУНДУКИ (CHESTS) ----------------
def add_chest(user_id, chest_type, amount=1):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO chests (user_id, chest_type, count) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, chest_type) DO UPDATE SET count = count + ?",
            (user_id, chest_type, amount, amount)
        )

def get_chests(user_id):
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT chest_type, count FROM chests WHERE user_id=? AND count > 0", (user_id,)).fetchall()
        return {r["chest_type"]: r["count"] for r in rows}

def try_spend_chest(user_id, chest_type, amount=1):
    with closing(get_conn()) as conn, conn:
        cur = conn.execute(
            "UPDATE chests SET count = count - ? WHERE user_id=? AND chest_type=? AND count >= ?",
            (amount, user_id, chest_type, amount)
        )
        return cur.rowcount > 0

# ---------------- EVENTS (boss) ----------------
def create_event(name, description, duration_seconds):
    now = int(time.time())
    with closing(get_conn()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO events (name, description, started_at, ends_at, active) VALUES (?, ?, ?, ?, 1)",
            (name, description, now, now + duration_seconds),
        )
        return cur.lastrowid

def get_active_event():
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT * FROM events WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

def add_event_damage(event_id, user_id, damage):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO event_damage (event_id, user_id, damage) VALUES (?, ?, ?) "
            "ON CONFLICT(event_id, user_id) DO UPDATE SET damage = damage + ?",
            (event_id, user_id, damage, damage),
        )

def get_event_leaderboard(event_id, limit=50):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT user_id, damage FROM event_damage WHERE event_id=? ORDER BY damage DESC LIMIT ?",
            (event_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

def get_all_event_participants(event_id):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT user_id, damage FROM event_damage WHERE event_id=? ORDER BY damage DESC",
            (event_id,),
        ).fetchall()
        return [dict(r) for r in rows]

def close_event(event_id):
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE events SET active=0 WHERE id=?", (event_id,))

# ---------------- ПРОМОКОДЫ ----------------
def try_redeem_promo(user_id, code, gold=0, dna_points=0, nautilus_shells=0, permanent_boost=False):
    with closing(get_conn()) as conn, conn:
        try:
            conn.execute(
                "INSERT INTO promo_redemptions (user_id, code, redeemed_at) VALUES (?, ?, ?)",
                (user_id, code, int(time.time())),
            )
        except sqlite3.IntegrityError:
            return False
        if permanent_boost:
            conn.execute(
                "UPDATE users SET gold = gold + ?, dna_points = dna_points + ?, "
                "nautilus_shells = nautilus_shells + ?, total_earned_gold = total_earned_gold + ?, "
                "permanent_boost = 1 WHERE user_id = ?",
                (gold, dna_points, nautilus_shells, gold, user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET gold = gold + ?, dna_points = dna_points + ?, "
                "nautilus_shells = nautilus_shells + ?, total_earned_gold = total_earned_gold + ? "
                "WHERE user_id = ?",
                (gold, dna_points, nautilus_shells, gold, user_id),
            )
        return True

async def add_to_buffer(redis, user_id: int, gold: int = 0, kills: int = 0, cur_meters: int = 0, max_meters: int = 0):
    """Добавляет фарм и метры во временный буфер Redis."""
    key = f"user_buffer:{user_id}"
    await redis.hincrby(key, "gold", gold)
    await redis.hincrby(key, "kills", kills)
    
    # Записываем текущую глубину, чтобы краб двигался вперед
    if cur_meters > 0:
        await redis.hset(key, "cur_meters", cur_meters)
        
    # Обновляем рекорд метров, только если он побит
    current_max = await redis.hget(key, "max_meters")
    current_max = int(current_max) if current_max else 0
    if max_meters > current_max:
        await redis.hset(key, "max_meters", max_meters)
        
    await redis.hset(key, "last_action_ts", int(time.time()))

async def flush_user_buffer(redis, user_id: int):
    """Сливает буфер из Redis в SQLite и очищает его."""
    key = f"user_buffer:{user_id}"
    buffer_data = await redis.hgetall(key)
    
    if not buffer_data:
        return False
        
    gold = int(buffer_data.get(b"gold", 0))
    kills = int(buffer_data.get(b"kills", 0))
    cur_meters = int(buffer_data.get(b"cur_meters", 0))
    max_meters = int(buffer_data.get(b"max_meters", 0))
    
    user = await run_async(get_user, user_id)
    if not user:
        return False
        
    new_max_meters = max(user["max_meters"], max_meters)
    new_cur_meters = cur_meters if cur_meters > 0 else user["cur_meters"]
    
    # Сохраняем в SQLite одним быстрым запросом
    await run_async(
        update_user, user_id,
        gold=user["gold"] + gold,
        total_earned_gold=user["total_earned_gold"] + gold,
        kills=user["kills"] + kills,
        cur_meters=new_cur_meters,
        max_meters=new_max_meters
    )
    
    await redis.delete(key)
    return True
