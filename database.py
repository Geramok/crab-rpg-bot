# -*- coding: utf-8 -*-
import sqlite3
import time
from contextlib import closing

from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _safe_migrate(conn, sql):
    try:
        conn.execute(sql)
    except sqlite3.OperationalError:
        pass  # колонка/индекс уже существует


def init_db():
    with closing(get_conn()) as conn, conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            nickname TEXT,
            crab_type INTEGER,
            shore INTEGER,
            crab_level INTEGER DEFAULT 1,
            gold INTEGER DEFAULT 0,
            dna_points INTEGER DEFAULT 0,
            molts INTEGER DEFAULT 0,
            max_meters INTEGER DEFAULT 0,
            cur_meters INTEGER DEFAULT 0,
            cur_hp INTEGER DEFAULT 0,
            in_hunt INTEGER DEFAULT 0,
            monster_json TEXT,
            kills INTEGER DEFAULT 0,
            boss_kills INTEGER DEFAULT 0,
            dig_start_ts INTEGER,
            dig_duration_seconds INTEGER,
            last_hp_regen_ts INTEGER,
            last_nick_change_ts INTEGER,
            registered_at INTEGER,
            total_earned_gold INTEGER DEFAULT 0,
            total_dna_earned INTEGER DEFAULT 0,
            nautilus_shells INTEGER DEFAULT 0,
            buff_damage_mult REAL,
            buff_expires_ts INTEGER,
            permanent_boost INTEGER DEFAULT 0,
            battle_message_id INTEGER
        )
        """)
        # Миграции для БД, созданных до появления этих полей
        for col, coltype in [
            ("dig_duration_seconds", "INTEGER"), ("last_hp_regen_ts", "INTEGER"),
            ("buff_damage_mult", "REAL"), ("buff_expires_ts", "INTEGER"),
            ("permanent_boost", "INTEGER DEFAULT 0"), ("battle_message_id", "INTEGER"),
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
        CREATE TABLE IF NOT EXISTS special_mutations (
            user_id INTEGER, key TEXT, equipped INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, key)
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            user_id INTEGER, key TEXT, count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, key)
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
        for slot in ("legs", "shell", "claws"):
            conn.execute(
                "INSERT OR IGNORE INTO mutations (user_id, slot, level, equipped) VALUES (?, ?, 0, 0)",
                (user_id, slot),
            )


def update_user(user_id, **fields):
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [user_id]
    with closing(get_conn()) as conn, conn:
        conn.execute(f"UPDATE users SET {keys} WHERE user_id=?", values)


def try_spend(user_id, field, amount):
    """Атомарно списывает amount из поля field, только если средств хватает.
    Защита от гонки при быстром двойном клике."""
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
    """Атомарно проверяет и списывает ресурсы по рецепту (recipe: {key: amount}).
    Возвращает True, если удалось (хватило всех ресурсов сразу)."""
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


# ---------------- MUTATIONS ----------------

def get_mutations(user_id):
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT * FROM mutations WHERE user_id=?", (user_id,)).fetchall()
        return {r["slot"]: dict(r) for r in rows}


def set_mutation(user_id, slot, level=None, equipped=None, variant_key=None):
    current = get_mutations(user_id).get(slot, {"level": 0, "equipped": 0, "variant_key": None})
    new_level = level if level is not None else current["level"]
    new_equipped = int(equipped) if equipped is not None else current["equipped"]
    new_variant = variant_key if variant_key is not None else current.get("variant_key")
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO mutations (user_id, slot, level, equipped, variant_key) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, slot) DO UPDATE SET level=?, equipped=?, variant_key=?",
            (user_id, slot, new_level, new_equipped, new_variant, new_level, new_equipped, new_variant),
        )


def get_special_mutations(user_id):
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT * FROM special_mutations WHERE user_id=?", (user_id,)).fetchall()
        return {r["key"]: dict(r) for r in rows}


def add_special_mutation(user_id, key):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT OR IGNORE INTO special_mutations (user_id, key, equipped) VALUES (?, ?, 0)",
            (user_id, key),
        )


def set_special_mutation_equipped(user_id, key, equipped):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE special_mutations SET equipped=? WHERE user_id=? AND key=?",
            (int(equipped), user_id, key),
        )


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
