"""
ZERO HOUR: SURVIVORS — single-file edition
=============================================
The complete game (server + client + database + shared protocol) in one
file, so you can just run:

    python game.py

The first run installs nothing extra beyond pygame (see requirements below);
it launches a local game server on 127.0.0.1:5555 in the background and then
opens the game window connected to it. Close the window and the server shuts
down with it.

To play with OTHER people across machines, you don't run two copies of this
file talking to each other's local servers — one person hosts, everyone else
joins that host:

    # On the host machine (starts the server only, no window):
    python game.py --host-only --port 5555

    # On every player's machine (joins that host, opens the game window):
    python game.py --join <host-ip> --port 5555

Requires: pip install pygame
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
import queue
import random
import sqlite3
import string
import struct
import sys
import threading
import time
import uuid
from datetime import datetime

try:
    import pygame
except ImportError:
    pygame = None  # only required for the client/window; --host-only doesn't need it

# In the original multi-file version, server.py and client.py both did
# `import shared as S` and referenced S.SOME_CONSTANT / S.some_function().
# Everything now lives in this one module, so `S` is just an alias for this
# module itself — every `S.xxx` reference below keeps working unchanged.
S = sys.modules[__name__]

# ============================================================================
# SECTION 1: Shared constants, map data, wire protocol
# ============================================================================

import json
import struct
import random

# --------------------------------------------------------------------------
# Networking: length-prefixed JSON frames over TCP (robust to partial reads)
# --------------------------------------------------------------------------

def pack_message(msg_type: str, data: dict) -> bytes:
    payload = json.dumps({"type": msg_type, "data": data}).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


class FrameBuffer:
    """Accumulates raw bytes from a socket and yields complete decoded messages."""

    def __init__(self):
        self.buf = b""

    def feed(self, chunk: bytes):
        self.buf += chunk

    def pop_messages(self):
        messages = []
        while True:
            if len(self.buf) < 4:
                break
            (length,) = struct.unpack(">I", self.buf[:4])
            if len(self.buf) < 4 + length:
                break
            raw = self.buf[4:4 + length]
            self.buf = self.buf[4 + length:]
            try:
                messages.append(json.loads(raw.decode("utf-8")))
            except json.JSONDecodeError:
                continue
        return messages


# --------------------------------------------------------------------------
# World / balance constants
# --------------------------------------------------------------------------

MAP_WIDTH = 2400
MAP_HEIGHT = 1800
TICK_RATE = 20                     # server ticks per second
PLAYER_SPEED = 220.0               # px/sec
PLAYER_MAX_HP = 100
BULLET_SPEED = 900.0
BULLET_DAMAGE = 18
BULLET_RANGE = 650
FIRE_COOLDOWN = 0.18                # seconds between shots
AI_MAX_HP = 60
AI_DAMAGE = 8
AI_SIGHT_RANGE = 320
AI_SPEED = 110.0
RESOURCE_COUNT = 14
MATCH_EXTRACTION_OPEN_AT = 90       # seconds into the match
MATCH_DISASTER_AT = 45              # seconds into the match
MATCH_HARD_END_AT = 240             # zero hour — match force-ends

GAME_MODES = {"solo": 1, "duo": 2, "squad": 4}

# City block layout expressed as rectangular obstacles: (x, y, w, h)
# A fictional abandoned city — "Meridian Hollow" — not based on any real map.
BUILDINGS = [
    (150, 150, 220, 160), (500, 120, 180, 220), (820, 180, 260, 140),
    (1200, 140, 200, 200), (1550, 160, 240, 180), (1900, 200, 220, 160),
    (150, 500, 260, 180), (520, 520, 200, 200), (850, 560, 220, 160),
    (1180, 520, 260, 200), (1560, 540, 200, 220), (1920, 520, 240, 180),
    (150, 900, 220, 200), (500, 920, 260, 160), (860, 950, 200, 200),
    (1220, 900, 220, 220), (1560, 930, 260, 160), (1900, 900, 220, 200),
    (150, 1300, 260, 200), (520, 1320, 200, 180), (850, 1350, 220, 160),
    (1200, 1300, 260, 220), (1560, 1340, 200, 180), (1900, 1300, 220, 200),
]

EXTRACTION_ZONE = {"x": MAP_WIDTH - 220, "y": MAP_HEIGHT - 220, "r": 110}

MISSION_TEMPLATES = [
    {"id": "eliminate", "desc": "Eliminate {n} hostile AI units", "target": 5},
    {"id": "collect", "desc": "Collect {n} supply crates", "target": 4},
    {"id": "hold", "desc": "Hold the Signal Tower for {n} seconds", "target": 40},
]

DISASTER_TYPES = ["toxic_fog", "structural_collapse", "electrical_storm"]


def random_spawn_point(rng: random.Random):
    while True:
        x = rng.randint(80, MAP_WIDTH - 80)
        y = rng.randint(80, MAP_HEIGHT - 80)
        if not any(bx <= x <= bx + bw and by <= y <= by + bh for bx, by, bw, bh in BUILDINGS):
            return x, y


def circle_rect_collides(cx, cy, r, rect):
    rx, ry, rw, rh = rect
    nearest_x = max(rx, min(cx, rx + rw))
    nearest_y = max(ry, min(cy, ry + rh))
    dx, dy = cx - nearest_x, cy - nearest_y
    return (dx * dx + dy * dy) < (r * r)

# ============================================================================
# SECTION 2: Persistence layer (accounts, Player IDs, profiles, friends)
# ============================================================================

"""
ZERO HOUR: SURVIVORS — Persistence Layer
------------------------------------------
Handles player accounts, unique Player IDs, profiles, stats, friends and teams.
Passwords are stored as salted SHA-256 hashes (swap for bcrypt/argon2 in production).
"""


DB_PATH = os.path.join(os.path.dirname(__file__), "data", "zero_hour.db")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


class Database:
    """Thread-safe wrapper around a single SQLite connection."""

    def __init__(self, path: str = DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #
    def _create_tables(self):
        with self._lock, self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS players (
                    player_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    level INTEGER DEFAULT 1,
                    xp INTEGER DEFAULT 0,
                    matches INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    kills INTEGER DEFAULT 0,
                    missions_completed INTEGER DEFAULT 0,
                    extractions INTEGER DEFAULT 0,
                    revives INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS friendships (
                    player_a TEXT NOT NULL,
                    player_b TEXT NOT NULL,
                    PRIMARY KEY (player_a, player_b)
                );

                CREATE TABLE IF NOT EXISTS friend_requests (
                    from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (from_id, to_id)
                );

                CREATE TABLE IF NOT EXISTS teams (
                    team_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    leader_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS team_members (
                    team_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    PRIMARY KEY (team_id, player_id)
                );
                """
            )

    # ------------------------------------------------------------------ #
    # Player ID generation
    # ------------------------------------------------------------------ #
    def _generate_player_id(self) -> str:
        with self._lock:
            cur = self.conn.cursor()
            while True:
                candidate = "ZH#" + "".join(random.choices(string.digits, k=5))
                cur.execute("SELECT 1 FROM players WHERE player_id = ?", (candidate,))
                if cur.fetchone() is None:
                    return candidate

    # ------------------------------------------------------------------ #
    # Accounts
    # ------------------------------------------------------------------ #
    def register(self, username: str, password: str):
        username = username.strip()
        if not (3 <= len(username) <= 20):
            return False, "Username must be 3-20 characters.", None
        if len(password) < 6:
            return False, "Password must be at least 6 characters.", None

        player_id = self._generate_player_id()
        salt = os.urandom(8).hex()
        pw_hash = _hash_password(password, salt)

        try:
            with self._lock, self.conn:
                self.conn.execute(
                    """INSERT INTO players
                       (player_id, username, password_hash, salt, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (player_id, username, pw_hash, salt, datetime.utcnow().isoformat()),
                )
            return True, "Account created.", player_id
        except sqlite3.IntegrityError:
            return False, "Username already taken.", None

    def login(self, username: str, password: str):
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM players WHERE username = ?", (username,)
            ).fetchone()
        if row is None:
            return False, "No such username.", None
        if _hash_password(password, row["salt"]) != row["password_hash"]:
            return False, "Incorrect password.", None
        return True, "Login successful.", row["player_id"]

    # ------------------------------------------------------------------ #
    # Profile / stats
    # ------------------------------------------------------------------ #
    PUBLIC_FIELDS = (
        "player_id, username, level, xp, matches, wins, kills, "
        "missions_completed, extractions, revives"
    )

    def get_profile(self, player_id: str):
        with self._lock:
            row = self.conn.execute(
                f"SELECT {self.PUBLIC_FIELDS} FROM players WHERE player_id = ?",
                (player_id,),
            ).fetchone()
        if row is None:
            return None
        profile = dict(row)
        profile["friends"] = len(self.get_friends(player_id))
        return profile

    def search_player(self, query: str):
        query = query.strip()
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT {self.PUBLIC_FIELDS} FROM players
                    WHERE player_id LIKE ? OR username LIKE ?
                    LIMIT 10""",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_stats(self, player_id: str, **deltas):
        """deltas: e.g. kills=1, wins=1, missions_completed=2 (added, not overwritten)."""
        allowed = {"matches", "wins", "kills", "missions_completed", "extractions",
                   "revives", "xp"}
        sets, values = [], []
        for k, v in deltas.items():
            if k in allowed:
                sets.append(f"{k} = {k} + ?")
                values.append(v)
        if not sets:
            return
        values.append(player_id)
        with self._lock, self.conn:
            self.conn.execute(
                f"UPDATE players SET {', '.join(sets)} WHERE player_id = ?", values
            )
        self._maybe_level_up(player_id)

    def _maybe_level_up(self, player_id: str):
        with self._lock:
            row = self.conn.execute(
                "SELECT xp, level FROM players WHERE player_id = ?", (player_id,)
            ).fetchone()
            if row is None:
                return
            needed = row["level"] * 100
            if row["xp"] >= needed:
                self.conn.execute(
                    "UPDATE players SET level = level + 1, xp = xp - ? WHERE player_id = ?",
                    (needed, player_id),
                )

    # ------------------------------------------------------------------ #
    # Friends
    # ------------------------------------------------------------------ #
    def send_friend_request(self, from_id: str, to_id: str):
        if from_id == to_id:
            return False, "Cannot friend yourself."
        if to_id in [f["player_id"] for f in self.get_friends(from_id)]:
            return False, "Already friends."
        try:
            with self._lock, self.conn:
                self.conn.execute(
                    "INSERT INTO friend_requests (from_id, to_id, created_at) VALUES (?, ?, ?)",
                    (from_id, to_id, datetime.utcnow().isoformat()),
                )
            return True, "Friend request sent."
        except sqlite3.IntegrityError:
            return False, "Request already pending."

    def respond_friend_request(self, to_id: str, from_id: str, accept: bool):
        with self._lock, self.conn:
            cur = self.conn.execute(
                "DELETE FROM friend_requests WHERE from_id = ? AND to_id = ?",
                (from_id, to_id),
            )
            if cur.rowcount == 0:
                return False, "No such request."
            if accept:
                a, b = sorted([from_id, to_id])
                self.conn.execute(
                    "INSERT OR IGNORE INTO friendships (player_a, player_b) VALUES (?, ?)",
                    (a, b),
                )
        return True, "Accepted." if accept else "Rejected."

    def get_pending_requests(self, player_id: str):
        with self._lock:
            rows = self.conn.execute(
                "SELECT from_id, created_at FROM friend_requests WHERE to_id = ?",
                (player_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_friends(self, player_id: str):
        with self._lock:
            rows = self.conn.execute(
                "SELECT player_a, player_b FROM friendships WHERE player_a = ? OR player_b = ?",
                (player_id, player_id),
            ).fetchall()
        friend_ids = [r["player_b"] if r["player_a"] == player_id else r["player_a"] for r in rows]
        return [self.get_profile(fid) for fid in friend_ids if self.get_profile(fid)]

# ============================================================================
# SECTION 3: Authoritative game server
# ============================================================================

"""
ZERO HOUR: SURVIVORS — Game Server
------------------------------------
Authoritative asyncio TCP server. Run this once (on your own machine, a VPS,
or any host with an open port) and any number of clients can connect to it —
over LAN immediately, or over the internet once the port is forwarded/opened.

Usage:
    python server.py [--host 0.0.0.0] [--port 5555]
"""




# ============================================================================
# Connection wrapper
# ============================================================================

class Connection:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.frame = S.FrameBuffer()
        self.player_id = None
        self.username = None
        self.room = None   # Room instance once joined

    async def send(self, msg_type, data):
        try:
            self.writer.write(S.pack_message(msg_type, data))
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass


# ============================================================================
# Room: pre-match lobby (Solo / Duo / Squad / Custom)
# ============================================================================

class Room:
    def __init__(self, room_id, mode, host_conn):
        self.room_id = room_id
        self.mode = mode
        self.capacity = S.GAME_MODES.get(mode, 4)
        self.members = [host_conn]
        self.match = None

    def player_ids(self):
        return [c.player_id for c in self.members]

    async def broadcast(self, msg_type, data):
        for c in self.members:
            await c.send(msg_type, data)

    async def broadcast_state(self):
        await self.broadcast("room_update", {
            "room_id": self.room_id,
            "mode": self.mode,
            "capacity": self.capacity,
            "players": self.player_ids(),
        })


# ============================================================================
# Live match simulation
# ============================================================================

class AIEnemy:
    def __init__(self, eid, x, y):
        self.id = eid
        self.x, self.y = x, y
        self.hp = S.AI_MAX_HP
        self.alive = True
        self.state = "patrol"
        self.target = None
        self.patrol_goal = (x, y)
        self.last_shot = 0.0

    def to_dict(self):
        return {"id": self.id, "x": round(self.x, 1), "y": round(self.y, 1),
                "hp": self.hp, "alive": self.alive}


class Resource:
    def __init__(self, rid, x, y, kind):
        self.id = rid
        self.x, self.y = x, y
        self.kind = kind  # "weapon" | "medkit" | "crate"
        self.collected = False

    def to_dict(self):
        return {"id": self.id, "x": self.x, "y": self.y, "kind": self.kind,
                "collected": self.collected}


class PlayerState:
    def __init__(self, conn: Connection, x, y):
        self.conn = conn
        self.player_id = conn.player_id
        self.username = conn.username
        self.x, self.y = x, y
        self.angle = 0.0
        self.hp = S.PLAYER_MAX_HP
        self.alive = True
        self.kills = 0
        self.ammo = 30
        self.last_shot = 0.0
        self.extracted = False

    def to_dict(self):
        return {
            "player_id": self.player_id, "username": self.username,
            "x": round(self.x, 1), "y": round(self.y, 1), "angle": round(self.angle, 2),
            "hp": self.hp, "alive": self.alive, "kills": self.kills,
            "ammo": self.ammo, "extracted": self.extracted,
        }


class Match:
    """One running game instance for a Room."""

    def __init__(self, room: Room, db: Database):
        self.room = room
        self.db = db
        self.rng = random.Random()
        self.start_time = time.time()
        self.players = {}
        for conn in room.members:
            sx, sy = S.random_spawn_point(self.rng)
            self.players[conn.player_id] = PlayerState(conn, sx, sy)

        self.enemies = {}
        for i in range(6 + len(room.members) * 2):
            ex, ey = S.random_spawn_point(self.rng)
            eid = f"ai_{i}"
            self.enemies[eid] = AIEnemy(eid, ex, ey)

        self.resources = {}
        kinds = ["weapon", "medkit", "crate"]
        for i in range(S.RESOURCE_COUNT):
            rx, ry = S.random_spawn_point(self.rng)
            rid = f"res_{i}"
            self.resources[rid] = Resource(rid, rx, ry, self.rng.choice(kinds))

        template = self.rng.choice(S.MISSION_TEMPLATES)
        self.mission = {
            "id": template["id"],
            "desc": template["desc"].format(n=template["target"]),
            "progress": 0,
            "target": template["target"],
            "complete": False,
        }
        self.disaster_active = False
        self.disaster_type = None
        self.disaster_zone = None
        self.ended = False
        self._bullets = []  # transient, for hit-scan resolution only

        self.task = None

    def elapsed(self):
        return time.time() - self.start_time

    # ---------------------------------------------------------------- #
    # Input handlers
    # ---------------------------------------------------------------- #
    def handle_move(self, player_id, dx, dy, angle, dt):
        p = self.players.get(player_id)
        if not p or not p.alive:
            return
        dist = math.hypot(dx, dy)
        if dist > 0:
            dx, dy = dx / dist, dy / dist
            nx = p.x + dx * S.PLAYER_SPEED * dt
            ny = p.y + dy * S.PLAYER_SPEED * dt
            if not any(S.circle_rect_collides(nx, ny, 14, b) for b in S.BUILDINGS):
                p.x = max(10, min(S.MAP_WIDTH - 10, nx))
                p.y = max(10, min(S.MAP_HEIGHT - 10, ny))
        p.angle = angle

    def handle_shoot(self, player_id, angle):
        p = self.players.get(player_id)
        if not p or not p.alive or p.ammo <= 0:
            return
        now = time.time()
        if now - p.last_shot < S.FIRE_COOLDOWN:
            return
        p.last_shot = now
        p.ammo -= 1
        p.angle = angle
        self._resolve_hitscan(p, angle)

    def _resolve_hitscan(self, shooter: PlayerState, angle):
        dx, dy = math.cos(angle), math.sin(angle)
        best_dist, best_target = S.BULLET_RANGE, None

        for other in self.players.values():
            if other is shooter or not other.alive:
                continue
            d = self._ray_hit_dist(shooter.x, shooter.y, dx, dy, other.x, other.y, 16)
            if d is not None and d < best_dist:
                best_dist, best_target = d, ("player", other)

        for enemy in self.enemies.values():
            if not enemy.alive:
                continue
            d = self._ray_hit_dist(shooter.x, shooter.y, dx, dy, enemy.x, enemy.y, 16)
            if d is not None and d < best_dist:
                best_dist, best_target = d, ("ai", enemy)

        if best_target is None:
            return
        kind, target = best_target
        target.hp -= S.BULLET_DAMAGE
        if target.hp <= 0 and target.alive:
            target.alive = False
            shooter.kills += 1
            if kind == "ai":
                if self.mission["id"] == "eliminate" and not self.mission["complete"]:
                    self.mission["progress"] += 1
                    if self.mission["progress"] >= self.mission["target"]:
                        self.mission["complete"] = True

    @staticmethod
    def _ray_hit_dist(ox, oy, dx, dy, tx, ty, radius):
        vx, vy = tx - ox, ty - oy
        proj = vx * dx + vy * dy
        if proj < 0 or proj > S.BULLET_RANGE:
            return None
        closest_x, closest_y = ox + dx * proj, oy + dy * proj
        if math.hypot(tx - closest_x, ty - closest_y) <= radius:
            return proj
        return None

    def handle_collect(self, player_id, resource_id):
        p = self.players.get(player_id)
        res = self.resources.get(resource_id)
        if not p or not res or res.collected or not p.alive:
            return
        if math.hypot(p.x - res.x, p.y - res.y) > 40:
            return
        res.collected = True
        if res.kind == "weapon":
            p.ammo = min(90, p.ammo + 30)
        elif res.kind == "medkit":
            p.hp = min(S.PLAYER_MAX_HP, p.hp + 35)
        elif res.kind == "crate":
            if self.mission["id"] == "collect" and not self.mission["complete"]:
                self.mission["progress"] += 1
                if self.mission["progress"] >= self.mission["target"]:
                    self.mission["complete"] = True

    def handle_revive(self, reviver_id, target_id):
        r = self.players.get(reviver_id)
        t = self.players.get(target_id)
        if not r or not t or t.alive or not r.alive:
            return
        if math.hypot(r.x - t.x, r.y - t.y) > 45:
            return
        t.alive = True
        t.hp = S.PLAYER_MAX_HP // 2
        self.db.update_stats(reviver_id, revives=1)

    def try_extract(self, player_id):
        p = self.players.get(player_id)
        if not p or not p.alive or p.extracted:
            return False
        if self.elapsed() < S.MATCH_EXTRACTION_OPEN_AT:
            return False
        z = S.EXTRACTION_ZONE
        if math.hypot(p.x - z["x"], p.y - z["y"]) <= z["r"]:
            p.extracted = True
            return True
        return False

    # ---------------------------------------------------------------- #
    # Simulation tick
    # ---------------------------------------------------------------- #
    def tick(self, dt):
        t = self.elapsed()

        # Disaster lifecycle
        if not self.disaster_active and t >= S.MATCH_DISASTER_AT:
            self.disaster_active = True
            self.disaster_type = self.rng.choice(S.DISASTER_TYPES)
            self.disaster_zone = {
                "x": self.rng.randint(400, S.MAP_WIDTH - 400),
                "y": self.rng.randint(400, S.MAP_HEIGHT - 400),
                "r": 180,
            }
        if self.disaster_active and self.disaster_zone:
            self.disaster_zone["r"] = min(420, self.disaster_zone["r"] + 6 * dt)
            for p in self.players.values():
                if not p.alive:
                    continue
                z = self.disaster_zone
                if math.hypot(p.x - z["x"], p.y - z["y"]) <= z["r"]:
                    p.hp -= 4 * dt
                    if p.hp <= 0:
                        p.hp = 0
                        p.alive = False

        # Hold-the-tower mission progress (tower = extraction zone for simplicity's own area)
        if self.mission["id"] == "hold" and not self.mission["complete"]:
            z = S.EXTRACTION_ZONE
            holding = any(
                p.alive and math.hypot(p.x - z["x"], p.y - z["y"]) <= z["r"]
                for p in self.players.values()
            )
            if holding:
                self.mission["progress"] = min(self.mission["target"], self.mission["progress"] + dt)
                if self.mission["progress"] >= self.mission["target"]:
                    self.mission["complete"] = True

        # AI enemy behaviour
        for enemy in self.enemies.values():
            if not enemy.alive:
                continue
            nearest, nearest_d = None, S.AI_SIGHT_RANGE
            for p in self.players.values():
                if not p.alive:
                    continue
                d = math.hypot(p.x - enemy.x, p.y - enemy.y)
                if d < nearest_d:
                    nearest, nearest_d = p, d

            if nearest:
                enemy.state = "attack"
                dx, dy = nearest.x - enemy.x, nearest.y - enemy.y
                dist = math.hypot(dx, dy) or 1
                if dist > 60:
                    nx = enemy.x + (dx / dist) * S.AI_SPEED * dt
                    ny = enemy.y + (dy / dist) * S.AI_SPEED * dt
                    if not any(S.circle_rect_collides(nx, ny, 12, b) for b in S.BUILDINGS):
                        enemy.x, enemy.y = nx, ny
                now = time.time()
                if now - enemy.last_shot > 1.0:
                    enemy.last_shot = now
                    nearest.hp -= S.AI_DAMAGE
                    if nearest.hp <= 0:
                        nearest.hp = 0
                        nearest.alive = False
            else:
                enemy.state = "patrol"
                gx, gy = enemy.patrol_goal
                if math.hypot(gx - enemy.x, gy - enemy.y) < 10:
                    enemy.patrol_goal = S.random_spawn_point(self.rng)
                else:
                    dx, dy = gx - enemy.x, gy - enemy.y
                    dist = math.hypot(dx, dy) or 1
                    nx = enemy.x + (dx / dist) * (S.AI_SPEED * 0.4) * dt
                    ny = enemy.y + (dy / dist) * (S.AI_SPEED * 0.4) * dt
                    if not any(S.circle_rect_collides(nx, ny, 12, b) for b in S.BUILDINGS):
                        enemy.x, enemy.y = nx, ny

        if t >= S.MATCH_HARD_END_AT:
            self.ended = True

        if all(not p.alive or p.extracted for p in self.players.values()):
            self.ended = True

    def snapshot(self):
        z = S.EXTRACTION_ZONE
        return {
            "elapsed": round(self.elapsed(), 1),
            "extraction_open": self.elapsed() >= S.MATCH_EXTRACTION_OPEN_AT,
            "extraction_zone": z,
            "players": [p.to_dict() for p in self.players.values()],
            "enemies": [e.to_dict() for e in self.enemies.values()],
            "resources": [r.to_dict() for r in self.resources.values()],
            "mission": self.mission,
            "disaster": {
                "active": self.disaster_active,
                "type": self.disaster_type,
                "zone": self.disaster_zone,
            },
            "buildings": S.BUILDINGS,
            "map": {"w": S.MAP_WIDTH, "h": S.MAP_HEIGHT},
            "ended": self.ended,
        }

    def finalize_stats(self):
        for p in self.players.values():
            self.db.update_stats(
                p.player_id,
                matches=1,
                wins=1 if p.extracted else 0,
                kills=p.kills,
                extractions=1 if p.extracted else 0,
                missions_completed=1 if self.mission["complete"] else 0,
                xp=20 + p.kills * 10 + (50 if p.extracted else 0),
            )


# ============================================================================
# Server
# ============================================================================

class GameServer:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.db = Database()
        self.connections = {}   # player_id -> Connection
        self.rooms = {}         # room_id -> Room

    async def start(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        addr = server.sockets[0].getsockname()
        print(f"[ZERO HOUR] Server listening on {addr}")
        async with server:
            await server.serve_forever()

    async def handle_client(self, reader, writer):
        conn = Connection(reader, writer)
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                conn.frame.feed(chunk)
                for msg in conn.frame.pop_messages():
                    await self.dispatch(conn, msg)
        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass
        finally:
            await self.on_disconnect(conn)

    async def on_disconnect(self, conn: Connection):
        if conn.player_id:
            self.connections.pop(conn.player_id, None)
        if conn.room and conn in conn.room.members:
            conn.room.members.remove(conn)
            if conn.room.members:
                await conn.room.broadcast_state()
            elif not conn.room.match:
                self.rooms.pop(conn.room.room_id, None)

    async def dispatch(self, conn: Connection, msg: dict):
        mtype = msg.get("type")
        data = msg.get("data", {})
        handler = getattr(self, f"h_{mtype}", None)
        if handler is None:
            await conn.send("error", {"message": f"Unknown message type '{mtype}'"})
            return
        try:
            await handler(conn, data)
        except Exception as e:
            await conn.send("error", {"message": str(e)})

    # ---------------------------------------------------------------- #
    # Account handlers
    # ---------------------------------------------------------------- #
    async def h_register(self, conn, data):
        ok, message, player_id = self.db.register(data.get("username", ""), data.get("password", ""))
        await conn.send("register_result", {"ok": ok, "message": message, "player_id": player_id})

    async def h_login(self, conn, data):
        ok, message, player_id = self.db.login(data.get("username", ""), data.get("password", ""))
        if ok:
            conn.player_id = player_id
            conn.username = data.get("username")
            self.connections[player_id] = conn
        await conn.send("login_result", {
            "ok": ok, "message": message, "player_id": player_id,
            "profile": self.db.get_profile(player_id) if ok else None,
        })

    async def h_get_profile(self, conn, data):
        pid = data.get("player_id", conn.player_id)
        profile = self.db.get_profile(pid)
        profile["online"] = pid in self.connections if profile else False
        await conn.send("profile_data", {"profile": profile})

    async def h_search_player(self, conn, data):
        results = self.db.search_player(data.get("query", ""))
        for r in results:
            r["online"] = r["player_id"] in self.connections
        await conn.send("search_result", {"results": results})

    # ---------------------------------------------------------------- #
    # Friends
    # ---------------------------------------------------------------- #
    async def h_friend_request(self, conn, data):
        ok, message = self.db.send_friend_request(conn.player_id, data.get("to_id"))
        await conn.send("friend_request_result", {"ok": ok, "message": message})
        target = self.connections.get(data.get("to_id"))
        if ok and target:
            await target.send("friend_request_received", {"from_id": conn.player_id, "from_username": conn.username})

    async def h_friend_respond(self, conn, data):
        ok, message = self.db.respond_friend_request(conn.player_id, data.get("from_id"), data.get("accept", False))
        await conn.send("friend_respond_result", {"ok": ok, "message": message})

    async def h_list_friends(self, conn, data):
        friends = self.db.get_friends(conn.player_id)
        for f in friends:
            f["online"] = f["player_id"] in self.connections
        pending = self.db.get_pending_requests(conn.player_id)
        await conn.send("friend_list", {"friends": friends, "pending": pending})

    # ---------------------------------------------------------------- #
    # Rooms / matchmaking
    # ---------------------------------------------------------------- #
    async def h_create_room(self, conn, data):
        mode = data.get("mode", "squad")
        room_id = "ZH-" + str(uuid.uuid4().int)[:4]
        room = Room(room_id, mode, conn)
        conn.room = room
        self.rooms[room_id] = room
        await conn.send("room_created", {"room_id": room_id, "mode": mode})
        await room.broadcast_state()

    async def h_join_room(self, conn, data):
        room = self.rooms.get(data.get("room_id"))
        if not room:
            await conn.send("error", {"message": "Room not found."})
            return
        if len(room.members) >= room.capacity:
            await conn.send("error", {"message": "Room is full."})
            return
        room.members.append(conn)
        conn.room = room
        await room.broadcast_state()

    async def h_quick_match(self, conn, data):
        """Solo/Duo/Squad public matchmaking — joins the first open room of that
        mode, or creates one."""
        mode = data.get("mode", "solo")
        for room in self.rooms.values():
            if room.mode == mode and not room.match and len(room.members) < room.capacity:
                room.members.append(conn)
                conn.room = room
                await room.broadcast_state()
                if len(room.members) == room.capacity:
                    await self.start_match(room)
                return
        room_id = "ZH-" + str(uuid.uuid4().int)[:4]
        room = Room(room_id, mode, conn)
        conn.room = room
        self.rooms[room_id] = room
        await conn.send("room_created", {"room_id": room_id, "mode": mode})
        await room.broadcast_state()
        if room.capacity == 1:
            await self.start_match(room)

    async def h_start_match(self, conn, data):
        room = conn.room
        if not room:
            await conn.send("error", {"message": "Not in a room."})
            return
        await self.start_match(room)

    async def start_match(self, room: Room):
        match = Match(room, self.db)
        room.match = match
        await room.broadcast("match_start", {
            "map": {"w": S.MAP_WIDTH, "h": S.MAP_HEIGHT},
            "buildings": S.BUILDINGS,
            "self_spawns": {p.player_id: (p.x, p.y) for p in match.players.values()},
        })
        match.task = asyncio.create_task(self.run_match_loop(room, match))

    async def run_match_loop(self, room: Room, match: Match):
        last = time.time()
        while not match.ended:
            now = time.time()
            dt = now - last
            last = now
            match.tick(dt)
            await room.broadcast("state_update", match.snapshot())
            await asyncio.sleep(1 / S.TICK_RATE)
        match.finalize_stats()
        await room.broadcast("match_end", match.snapshot())
        room.match = None
        self.rooms.pop(room.room_id, None)

    # ---------------------------------------------------------------- #
    # In-match input
    # ---------------------------------------------------------------- #
    async def h_move(self, conn, data):
        room = conn.room
        if not room or not room.match:
            return
        room.match.handle_move(conn.player_id, data.get("dx", 0), data.get("dy", 0),
                                data.get("angle", 0), data.get("dt", 1 / S.TICK_RATE))

    async def h_shoot(self, conn, data):
        room = conn.room
        if room and room.match:
            room.match.handle_shoot(conn.player_id, data.get("angle", 0))

    async def h_collect(self, conn, data):
        room = conn.room
        if room and room.match:
            room.match.handle_collect(conn.player_id, data.get("resource_id"))

    async def h_revive(self, conn, data):
        room = conn.room
        if room and room.match:
            room.match.handle_revive(conn.player_id, data.get("target_id"))

    async def h_extract(self, conn, data):
        room = conn.room
        if room and room.match:
            room.match.try_extract(conn.player_id)

    # ---------------------------------------------------------------- #
    # Chat
    # ---------------------------------------------------------------- #
    async def h_chat(self, conn, data):
        text = str(data.get("text", ""))[:280]
        room = conn.room
        payload = {"from": conn.username, "player_id": conn.player_id, "text": text}
        if room:
            await room.broadcast("chat_message", payload)
        else:
            await conn.send("chat_message", payload)


# ============================================================================
# SECTION 4: Pygame client
# ============================================================================

"""
ZERO HOUR: SURVIVORS — Client
--------------------------------
Pygame front-end. Networking runs on a background asyncio thread and talks to
the main render/input loop through thread-safe queues, so the UI never blocks
on the socket.

Usage:
    python client.py [--host 127.0.0.1] [--port 5555]
"""




# ---------------------------------------------------------------------------
# Colours (own palette — not copied from any existing game)
# ---------------------------------------------------------------------------
BG = (18, 22, 20)
PANEL = (28, 34, 31)
ACCENT = (120, 220, 130)
ACCENT_DARK = (70, 140, 80)
WARN = (230, 90, 70)
TEXT = (220, 230, 224)
MUTED = (140, 150, 145)
BUILDING_COLOR = (55, 60, 58)
GRID_COLOR = (26, 32, 29)
DISASTER_COLOR = (180, 60, 40)
EXTRACT_COLOR = (90, 180, 230)

FONT_NAME = None  # default pygame font


# ===========================================================================
# Networking thread
# ===========================================================================

class NetClient:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.inbound = queue.Queue()
        self.outbound = queue.Queue()
        self.connected = False
        self._loop = None
        self._writer = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self):
        try:
            reader, writer = await asyncio.open_connection(self.host, self.port)
        except OSError as e:
            self.inbound.put({"type": "conn_error", "data": {"message": str(e)}})
            return
        self._writer = writer
        self.connected = True
        self.inbound.put({"type": "connected", "data": {}})

        async def reader_task():
            frame = S.FrameBuffer()
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    self.inbound.put({"type": "disconnected", "data": {}})
                    return
                frame.feed(chunk)
                for msg in frame.pop_messages():
                    self.inbound.put(msg)

        async def writer_task():
            while True:
                msg_type, data = await self._loop.run_in_executor(None, self.outbound.get)
                try:
                    writer.write(S.pack_message(msg_type, data))
                    await writer.drain()
                except (ConnectionResetError, BrokenPipeError):
                    return

        await asyncio.gather(reader_task(), writer_task())

    def send(self, msg_type, data=None):
        self.outbound.put((msg_type, data or {}))

    def poll(self):
        msgs = []
        while True:
            try:
                msgs.append(self.inbound.get_nowait())
            except queue.Empty:
                break
        return msgs


# ===========================================================================
# Small UI helpers
# ===========================================================================

class TextInput:
    def __init__(self, rect, placeholder="", password=False):
        self.rect = pygame.Rect(rect)
        self.text = ""
        self.placeholder = placeholder
        self.password = password
        self.active = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                pass
            elif len(self.text) < 24 and event.unicode.isprintable():
                self.text += event.unicode

    def draw(self, surf, font):
        pygame.draw.rect(surf, PANEL, self.rect, border_radius=6)
        border = ACCENT if self.active else (60, 65, 62)
        pygame.draw.rect(surf, border, self.rect, width=2, border_radius=6)
        shown = "*" * len(self.text) if self.password else self.text
        label = shown if shown else self.placeholder
        color = TEXT if shown else MUTED
        surf.blit(font.render(label, True, color), (self.rect.x + 10, self.rect.y + 8))


class Button:
    def __init__(self, rect, label, color=ACCENT):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.color = color

    def draw(self, surf, font):
        hovered = self.rect.collidepoint(pygame.mouse.get_pos())
        c = tuple(min(255, v + 25) for v in self.color) if hovered else self.color
        pygame.draw.rect(surf, c, self.rect, border_radius=8)
        text_surf = font.render(self.label, True, (14, 16, 15))
        surf.blit(text_surf, text_surf.get_rect(center=self.rect.center))

    def clicked(self, event):
        return event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos)


# ===========================================================================
# Main application / state machine
# ===========================================================================

class App:
    STATE_LOGIN = "login"
    STATE_MENU = "menu"
    STATE_LOBBY = "lobby"
    STATE_MATCH = "match"
    STATE_END = "end"

    def __init__(self, host, port):
        if pygame is None:
            print("[ZERO HOUR] pygame is not installed. Run: pip install pygame")
            sys.exit(1)
        pygame.init()
        pygame.display.set_caption("ZERO HOUR: SURVIVORS")
        self.screen = pygame.display.set_mode((1200, 800))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(FONT_NAME, 20)
        self.font_big = pygame.font.SysFont(FONT_NAME, 40, bold=True)
        self.font_small = pygame.font.SysFont(FONT_NAME, 15)

        self.net = NetClient(host, port)
        self.state = self.STATE_LOGIN
        self.status_message = "Connecting to server..."

        self.username_input = TextInput((450, 300, 300, 40), "Username")
        self.password_input = TextInput((450, 360, 300, 40), "Password", password=True)
        self.login_btn = Button((450, 420, 140, 44), "LOGIN")
        self.register_btn = Button((610, 420, 140, 44), "REGISTER")

        self.player_id = None
        self.username = None
        self.profile = None
        self.friends = []
        self.pending_requests = []
        self.chat_log = []
        self.chat_input = TextInput((20, 740, 500, 32), "Press Enter to chat...")
        self.chat_active = False

        self.room_id = None
        self.room_players = []
        self.mode_buttons = {
            "solo": Button((450, 260, 300, 50), "SOLO"),
            "duo": Button((450, 320, 300, 50), "DUO"),
            "squad": Button((450, 380, 300, 50), "SQUAD"),
        }
        self.custom_room_input = TextInput((450, 460, 200, 40), "Room code")
        self.join_btn = Button((660, 460, 90, 40), "JOIN")
        self.create_custom_btn = Button((450, 510, 300, 40), "CREATE PRIVATE ROOM")
        self.search_input = TextInput((450, 570, 300, 40), "Search Player ID / name")
        self.search_btn = Button((760, 570, 90, 40), "FIND")
        self.search_results = []

        self.match_state = None
        self.camera = [0, 0]
        self.keys_down = set()
        self.last_move_send = 0

    # ------------------------------------------------------------------ #
    # Networking message handling
    # ------------------------------------------------------------------ #
    def handle_messages(self):
        for msg in self.net.poll():
            mtype, data = msg.get("type"), msg.get("data", {})

            if mtype == "connected":
                self.status_message = "Connected. Please log in or register."
            elif mtype == "conn_error":
                self.status_message = f"Connection failed: {data.get('message')}"
            elif mtype == "disconnected":
                self.status_message = "Disconnected from server."

            elif mtype == "register_result":
                if data["ok"]:
                    self.status_message = f"Account created! Your Player ID is {data['player_id']}. Now log in."
                else:
                    self.status_message = data["message"]

            elif mtype == "login_result":
                if data["ok"]:
                    self.player_id = data["player_id"]
                    self.username = self.username_input.text
                    self.profile = data["profile"]
                    self.state = self.STATE_MENU
                    self.net.send("list_friends")
                else:
                    self.status_message = data["message"]

            elif mtype == "profile_data":
                self.profile = data["profile"]

            elif mtype == "search_result":
                self.search_results = data["results"]

            elif mtype == "friend_list":
                self.friends = data["friends"]
                self.pending_requests = data["pending"]

            elif mtype == "friend_request_received":
                self.status_message = f"Friend request from {data['from_username']} ({data['from_id']})"

            elif mtype == "room_created":
                self.room_id = data["room_id"]
                self.state = self.STATE_LOBBY

            elif mtype == "room_update":
                self.room_id = data["room_id"]
                self.room_players = data["players"]
                self.state = self.STATE_LOBBY

            elif mtype == "match_start":
                self.state = self.STATE_MATCH
                self.match_state = None

            elif mtype == "state_update":
                self.match_state = data
                me = next((p for p in data["players"] if p["player_id"] == self.player_id), None)
                if me:
                    self.camera = [me["x"] - 600, me["y"] - 400]

            elif mtype == "match_end":
                self.match_state = data
                self.state = self.STATE_END

            elif mtype == "chat_message":
                self.chat_log.append(f"{data['from']}: {data['text']}")
                self.chat_log = self.chat_log[-8:]

            elif mtype == "error":
                self.status_message = data.get("message", "Error")

    # ------------------------------------------------------------------ #
    # State: LOGIN
    # ------------------------------------------------------------------ #
    def draw_login(self):
        title = self.font_big.render("ZERO HOUR: SURVIVORS", True, ACCENT)
        self.screen.blit(title, title.get_rect(center=(600, 180)))
        sub = self.font.render("Meridian Hollow awaits. Survive. Extract. Escape Zero Hour.", True, MUTED)
        self.screen.blit(sub, sub.get_rect(center=(600, 220)))

        self.username_input.draw(self.screen, self.font)
        self.password_input.draw(self.screen, self.font)
        self.login_btn.draw(self.screen, self.font)
        self.register_btn.draw(self.screen, self.font)

        msg = self.font.render(self.status_message, True, TEXT)
        self.screen.blit(msg, msg.get_rect(center=(600, 500)))

    def handle_login_event(self, event):
        self.username_input.handle_event(event)
        self.password_input.handle_event(event)
        if self.login_btn.clicked(event):
            self.net.send("login", {"username": self.username_input.text,
                                     "password": self.password_input.text})
        if self.register_btn.clicked(event):
            self.net.send("register", {"username": self.username_input.text,
                                        "password": self.password_input.text})

    # ------------------------------------------------------------------ #
    # State: MENU (profile / friends / search / mode select)
    # ------------------------------------------------------------------ #
    def draw_menu(self):
        pygame.draw.rect(self.screen, PANEL, (20, 20, 380, 300), border_radius=10)
        if self.profile:
            p = self.profile
            lines = [
                f"{self.username}",
                f"{self.player_id}",
                f"Level {p['level']}   XP {p['xp']}",
                "",
                f"Matches: {p['matches']}    Wins: {p['wins']}",
                f"Kills: {p['kills']}",
                f"Missions Completed: {p['missions_completed']}",
                f"Successful Extractions: {p['extractions']}",
                f"Revives: {p['revives']}",
                f"Friends: {p['friends']}",
            ]
            for i, line in enumerate(lines):
                color = ACCENT if i == 0 else (MUTED if i == 1 else TEXT)
                f = self.font_big if i == 0 else self.font
                self.screen.blit(f.render(line, True, color), (40, 40 + i * 26))

        for btn in self.mode_buttons.values():
            btn.draw(self.screen, self.font)
        self.custom_room_input.draw(self.screen, self.font)
        self.join_btn.draw(self.screen, self.font)
        self.create_custom_btn.draw(self.screen, self.font)

        self.search_input.draw(self.screen, self.font)
        self.search_btn.draw(self.screen, self.font)
        for i, r in enumerate(self.search_results[:5]):
            dot = ACCENT if r.get("online") else MUTED
            pygame.draw.circle(self.screen, dot, (460, 625 + i * 24), 4)
            line = f"{r['username']}  {r['player_id']}  Lv{r['level']}"
            self.screen.blit(self.font_small.render(line, True, TEXT), (475, 615 + i * 24))

        pygame.draw.rect(self.screen, PANEL, (830, 20, 350, 400), border_radius=10)
        self.screen.blit(self.font.render("FRIENDS", True, ACCENT), (850, 35))
        for i, f in enumerate(self.friends[:10]):
            dot = ACCENT if f.get("online") else MUTED
            pygame.draw.circle(self.screen, dot, (850, 75 + i * 26), 4)
            line = f"{f['username']}  Lv{f['level']}"
            self.screen.blit(self.font_small.render(line, True, TEXT), (865, 66 + i * 26))
        if self.pending_requests:
            self.screen.blit(self.font.render("Pending requests: " + ", ".join(
                r["from_id"] for r in self.pending_requests), True, WARN), (850, 350))

        msg = self.font.render(self.status_message, True, MUTED)
        self.screen.blit(msg, (20, 760))

    def handle_menu_event(self, event):
        self.custom_room_input.handle_event(event)
        self.search_input.handle_event(event)

        if self.mode_buttons["solo"].clicked(event):
            self.net.send("quick_match", {"mode": "solo"})
        if self.mode_buttons["duo"].clicked(event):
            self.net.send("quick_match", {"mode": "duo"})
        if self.mode_buttons["squad"].clicked(event):
            self.net.send("quick_match", {"mode": "squad"})
        if self.create_custom_btn.clicked(event):
            self.net.send("create_room", {"mode": "squad"})
        if self.join_btn.clicked(event) and self.custom_room_input.text:
            self.net.send("join_room", {"room_id": self.custom_room_input.text.upper()})
        if self.search_btn.clicked(event) and self.search_input.text:
            self.net.send("search_player", {"query": self.search_input.text})

        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            if self.search_input.active and self.search_input.text:
                self.net.send("search_player", {"query": self.search_input.text})

    # ------------------------------------------------------------------ #
    # State: LOBBY
    # ------------------------------------------------------------------ #
    def draw_lobby(self):
        title = self.font_big.render(f"ROOM {self.room_id}", True, ACCENT)
        self.screen.blit(title, title.get_rect(center=(600, 150)))
        sub = self.font.render("Share this Room ID with friends to squad up.", True, MUTED)
        self.screen.blit(sub, sub.get_rect(center=(600, 195)))
        for i, pid in enumerate(self.room_players):
            tag = " (you)" if pid == self.player_id else ""
            line = self.font.render(f"• {pid}{tag}", True, TEXT)
            self.screen.blit(line, (520, 250 + i * 30))
        start_btn = Button((500, 500, 200, 50), "START MATCH")
        start_btn.draw(self.screen, self.font)
        self._lobby_start_btn = start_btn

    def handle_lobby_event(self, event):
        if getattr(self, "_lobby_start_btn", None) and self._lobby_start_btn.clicked(event):
            self.net.send("start_match")

    # ------------------------------------------------------------------ #
    # State: MATCH (top-down render)
    # ------------------------------------------------------------------ #
    def world_to_screen(self, x, y):
        return x - self.camera[0], y - self.camera[1]

    def draw_match(self):
        self.screen.fill(BG)
        if not self.match_state:
            wait = self.font.render("Loading match...", True, TEXT)
            self.screen.blit(wait, wait.get_rect(center=(600, 400)))
            return
        st = self.match_state

        for gx in range(0, S.MAP_WIDTH, 100):
            sx, _ = self.world_to_screen(gx, 0)
            pygame.draw.line(self.screen, GRID_COLOR, (sx, 0), (sx, 800))
        for gy in range(0, S.MAP_HEIGHT, 100):
            _, sy = self.world_to_screen(0, gy)
            pygame.draw.line(self.screen, GRID_COLOR, (0, sy), (1200, sy))

        for (bx, by, bw, bh) in st["buildings"]:
            sx, sy = self.world_to_screen(bx, by)
            pygame.draw.rect(self.screen, BUILDING_COLOR, (sx, sy, bw, bh), border_radius=4)

        z = st["extraction_zone"]
        sx, sy = self.world_to_screen(z["x"], z["y"])
        color = EXTRACT_COLOR if st["extraction_open"] else (70, 90, 100)
        pygame.draw.circle(self.screen, color, (int(sx), int(sy)), int(z["r"]), width=3)
        label = self.font_small.render(
            "EXTRACTION OPEN" if st["extraction_open"] else "Extraction opening soon...",
            True, color)
        self.screen.blit(label, (sx - 60, sy - z["r"] - 20))

        if st["disaster"]["active"] and st["disaster"]["zone"]:
            dz = st["disaster"]["zone"]
            dsx, dsy = self.world_to_screen(dz["x"], dz["y"])
            surf = pygame.Surface((1200, 800), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*DISASTER_COLOR, 70), (int(dsx), int(dsy)), int(dz["r"]))
            self.screen.blit(surf, (0, 0))
            pygame.draw.circle(self.screen, DISASTER_COLOR, (int(dsx), int(dsy)), int(dz["r"]), width=2)

        for r in st["resources"]:
            if r["collected"]:
                continue
            rsx, rsy = self.world_to_screen(r["x"], r["y"])
            colors = {"weapon": (230, 200, 90), "medkit": (90, 220, 140), "crate": (170, 140, 220)}
            pygame.draw.circle(self.screen, colors.get(r["kind"], TEXT), (int(rsx), int(rsy)), 8)

        for e in st["enemies"]:
            if not e["alive"]:
                continue
            esx, esy = self.world_to_screen(e["x"], e["y"])
            pygame.draw.circle(self.screen, WARN, (int(esx), int(esy)), 12)
            pygame.draw.rect(self.screen, (60, 20, 20), (esx - 15, esy - 24, 30, 4))
            pygame.draw.rect(self.screen, WARN, (esx - 15, esy - 24, 30 * (e["hp"] / S.AI_MAX_HP), 4))

        me = None
        for p in st["players"]:
            psx, psy = self.world_to_screen(p["x"], p["y"])
            if not p["alive"]:
                pygame.draw.circle(self.screen, MUTED, (int(psx), int(psy)), 10, width=2)
                continue
            color = ACCENT if p["player_id"] == self.player_id else (200, 200, 90)
            pygame.draw.circle(self.screen, color, (int(psx), int(psy)), 12)
            end = (psx + math.cos(p["angle"]) * 22, psy + math.sin(p["angle"]) * 22)
            pygame.draw.line(self.screen, color, (psx, psy), end, 3)
            name = self.font_small.render(p["username"], True, TEXT)
            self.screen.blit(name, (psx - 20, psy - 30))
            pygame.draw.rect(self.screen, (60, 20, 20), (psx - 15, psy - 24, 30, 4))
            pygame.draw.rect(self.screen, ACCENT, (psx - 15, psy - 24, 30 * (p["hp"] / S.PLAYER_MAX_HP), 4))
            if p["player_id"] == self.player_id:
                me = p

        # HUD
        pygame.draw.rect(self.screen, PANEL, (0, 0, 1200, 60))
        if me:
            hud = f"HP {int(me['hp'])}   AMMO {me['ammo']}   KILLS {me['kills']}"
            self.screen.blit(self.font.render(hud, True, TEXT), (20, 18))
        mission = st["mission"]
        mtext = f"MISSION: {mission['desc']}  [{int(mission['progress'])}/{mission['target']}]"
        if mission["complete"]:
            mtext += "  ✓ COMPLETE"
        self.screen.blit(self.font.render(mtext, True, ACCENT), (350, 18))
        timer = f"T+{int(st['elapsed'])}s   ZERO HOUR AT {S.MATCH_HARD_END_AT}s"
        self.screen.blit(self.font_small.render(timer, True, MUTED), (950, 22))

        if st["disaster"]["active"]:
            warn = self.font.render(f"⚠ DISASTER: {st['disaster']['type'].upper()}", True, WARN)
            self.screen.blit(warn, (350, 70))

        controls = self.font_small.render(
            "WASD move · Mouse aim · Left-click shoot · E collect/revive · F extract · Enter chat",
            True, MUTED)
        self.screen.blit(controls, (20, 775))

        for i, line in enumerate(self.chat_log):
            self.screen.blit(self.font_small.render(line, True, TEXT), (20, 700 - (len(self.chat_log) - i) * 18))
        if self.chat_active:
            self.chat_input.draw(self.screen, self.font)

    def handle_match_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            if self.chat_active and self.chat_input.text:
                self.net.send("chat", {"text": self.chat_input.text})
                self.chat_input.text = ""
                self.chat_active = False
            else:
                self.chat_active = True
                self.chat_input.active = True
            return
        if self.chat_active:
            self.chat_input.handle_event(event)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = pygame.mouse.get_pos()
            me = self._me()
            if me:
                angle = math.atan2(my - (me["y"] - self.camera[1]), mx - (me["x"] - self.camera[0]))
                self.net.send("shoot", {"angle": angle})
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_e:
                self._try_interact()
            if event.key == pygame.K_f:
                self.net.send("extract")

    def _me(self):
        if not self.match_state:
            return None
        return next((p for p in self.match_state["players"] if p["player_id"] == self.player_id), None)

    def _try_interact(self):
        me = self._me()
        if not me or not self.match_state:
            return
        for r in self.match_state["resources"]:
            if r["collected"]:
                continue
            if math.hypot(me["x"] - r["x"], me["y"] - r["y"]) < 45:
                self.net.send("collect", {"resource_id": r["id"]})
                return
        for p in self.match_state["players"]:
            if p["player_id"] != self.player_id and not p["alive"]:
                if math.hypot(me["x"] - p["x"], me["y"] - p["y"]) < 50:
                    self.net.send("revive", {"target_id": p["player_id"]})
                    return

    def send_movement(self):
        if self.chat_active or not self.match_state:
            return
        now = time.time()
        dt = now - self.last_move_send if self.last_move_send else 1 / S.TICK_RATE
        self.last_move_send = now
        dx = (1 if pygame.K_d in self.keys_down else 0) - (1 if pygame.K_a in self.keys_down else 0)
        dy = (1 if pygame.K_s in self.keys_down else 0) - (1 if pygame.K_w in self.keys_down else 0)
        me = self._me()
        angle = 0.0
        if me:
            mx, my = pygame.mouse.get_pos()
            angle = math.atan2(my - (me["y"] - self.camera[1]), mx - (me["x"] - self.camera[0]))
        if dx or dy or angle:
            self.net.send("move", {"dx": dx, "dy": dy, "angle": angle, "dt": min(dt, 0.1)})

    # ------------------------------------------------------------------ #
    # State: END
    # ------------------------------------------------------------------ #
    def draw_end(self):
        st = self.match_state
        title = self.font_big.render("ZERO HOUR", True, WARN)
        self.screen.blit(title, title.get_rect(center=(600, 150)))
        if st:
            me = next((p for p in st["players"] if p["player_id"] == self.player_id), None)
            if me:
                result = "EXTRACTED — SURVIVED" if me["extracted"] else "DID NOT MAKE IT OUT"
                col = ACCENT if me["extracted"] else WARN
                self.screen.blit(self.font_big.render(result, True, col),
                                  self.font_big.render(result, True, col).get_rect(center=(600, 230)))
                stats = f"Kills: {me['kills']}   Mission complete: {st['mission']['complete']}"
                self.screen.blit(self.font.render(stats, True, TEXT),
                                  self.font.render(stats, True, TEXT).get_rect(center=(600, 290)))
        cont = Button((500, 400, 200, 50), "RETURN TO MENU")
        cont.draw(self.screen, self.font)
        self._end_btn = cont

    def handle_end_event(self, event):
        if getattr(self, "_end_btn", None) and self._end_btn.clicked(event):
            self.state = self.STATE_MENU
            self.net.send("get_profile", {"player_id": self.player_id})
            self.net.send("list_friends")

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            self.handle_messages()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    self.keys_down.add(event.key)
                if event.type == pygame.KEYUP:
                    self.keys_down.discard(event.key)

                if self.state == self.STATE_LOGIN:
                    self.handle_login_event(event)
                elif self.state == self.STATE_MENU:
                    self.handle_menu_event(event)
                elif self.state == self.STATE_LOBBY:
                    self.handle_lobby_event(event)
                elif self.state == self.STATE_MATCH:
                    self.handle_match_event(event)
                elif self.state == self.STATE_END:
                    self.handle_end_event(event)

            if self.state == self.STATE_MATCH:
                self.send_movement()

            self.screen.fill(BG)
            if self.state == self.STATE_LOGIN:
                self.draw_login()
            elif self.state == self.STATE_MENU:
                self.draw_menu()
            elif self.state == self.STATE_LOBBY:
                self.draw_lobby()
            elif self.state == self.STATE_MATCH:
                self.draw_match()
            elif self.state == self.STATE_END:
                self.draw_end()

            pygame.display.flip()
        pygame.quit()


# ============================================================================
# SECTION 5: Unified entry point
# ============================================================================

def _run_server_forever(host, port):
    """Runs the authoritative server on its own asyncio loop. Used both for
    --host-only mode (this call blocks, no client is opened) and for the
    default local quick-play mode (called on a background thread)."""
    server = GameServer(host, port)
    asyncio.run(server.start())


def _wait_for_port(host, port, timeout=5.0):
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def main():
    parser = argparse.ArgumentParser(
        description="ZERO HOUR: SURVIVORS — run with no arguments to just play."
    )
    parser.add_argument("--join", metavar="HOST",
                         help="Connect to a game already hosted at this IP instead of "
                              "starting a local server (use this to play with others).")
    parser.add_argument("--host-only", action="store_true",
                         help="Run only the server (no game window) — use this on the "
                              "machine that will host a multiplayer match.")
    parser.add_argument("--port", type=int, default=5555)
    args = parser.parse_args()

    if args.host_only:
        print(f"[ZERO HOUR] Hosting on 0.0.0.0:{args.port} — share your IP with other "
              f"players and have them run: python game.py --join <this-machine-ip> "
              f"--port {args.port}")
        _run_server_forever("0.0.0.0", args.port)
        return

    if args.join:
        print(f"[ZERO HOUR] Connecting to {args.join}:{args.port} ...")
        App(args.join, args.port).run()
        return

    # Default: quick local play — start a server on localhost in the
    # background, then open the game window connected to it.
    host, port = "127.0.0.1", args.port
    print(f"[ZERO HOUR] Starting local server on {host}:{port} ...")
    server_thread = threading.Thread(target=_run_server_forever, args=(host, port), daemon=True)
    server_thread.start()

    if not _wait_for_port(host, port, timeout=5.0):
        print("[ZERO HOUR] Server did not start in time. Is the port already in use? "
              f"Try: python game.py --port {port + 1}")
        sys.exit(1)

    print("[ZERO HOUR] Server ready. Launching game window...")
    App(host, port).run()
    # The App's window closing ends the process; the daemon server thread
    # is torn down automatically when the process exits.


if __name__ == "__main__":
    main()