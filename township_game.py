"""
================================================================================
ROBOT PUZZLE ADVENTURE & TOWNSHIP BUILDER
A single-file Pygame project.

    PLAY PUZZLE -> EARN COINS/PARTS -> BUILD -> GROW POPULATION
    -> UNLOCK -> EXPAND -> REPEAT

HOW TO RUN
    pip install pygame
    python township_game.py

FILE LAYOUT (read top to bottom - it mirrors the architecture)
    SECTION 1  Config & colours
    SECTION 2  Static game data     (buildings, crops, puzzles, missions)
    SECTION 3  Game engine          (pure-ish logic, no drawing at all)
    SECTION 4  Save / load
    SECTION 5  UI toolkit           (buttons, panels, toasts, sprites)
    SECTION 6  Puzzle mini-games    (10 of them, one class each)
    SECTION 7  Screens              (map, puzzles, build, farm, robot, missions)
    SECTION 8  Application loop
================================================================================
"""

import json
import math
import os
import random
import time

import pygame

# ==============================================================================
# SECTION 1 - CONFIG & COLOURS
# ==============================================================================

SCREEN_W, SCREEN_H = 1100, 720
FPS = 60
SAVE_FILE = "township_save.json"
SAVE_VERSION = 1

# Township map grid
GRID_W, GRID_H = 14, 9
TILE = 56
MAP_X, MAP_Y = 30, 126

HUD_H = 64
NAV_H = 62

# --- palette (friendly cartoon village) ---
C_SKY        = (168, 216, 234)
C_GRASS      = (140, 200, 120)
C_GRASS_ALT  = (132, 192, 112)
C_GRASS_HL   = (180, 226, 150)
C_DIRT       = (196, 164, 116)
C_ROAD       = (150, 146, 140)
C_WATER      = (108, 178, 220)
C_PANEL      = (255, 252, 244)
C_PANEL_DARK = (238, 232, 218)
C_INK        = (58, 52, 48)
C_INK_SOFT   = (126, 118, 110)
C_GOLD       = (245, 196, 66)
C_GOLD_DARK  = (206, 154, 32)
C_GREEN      = (92, 184, 100)
C_GREEN_DARK = (62, 142, 74)
C_RED        = (226, 98, 88)
C_BLUE       = (86, 150, 226)
C_PURPLE     = (162, 116, 214)
C_ORANGE     = (240, 148, 70)
C_PINK       = (238, 138, 168)
C_WHITE      = (255, 255, 255)
C_SHADOW     = (0, 0, 0, 40)
C_LOCK       = (176, 170, 162)

PUZZLE_COLORS = [C_RED, C_BLUE, C_GREEN, C_GOLD, C_PURPLE, C_ORANGE]

DIFFICULTIES = ["easy", "medium", "hard"]
DIFF_LABEL = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}
DIFF_XP = {"easy": 10, "medium": 25, "hard": 50}


# ==============================================================================
# SECTION 2 - STATIC GAME DATA
# All balance numbers live here. Never hard-code a price inside a screen.
# ==============================================================================

# ---- Robot parts -------------------------------------------------------------
PART_ORDER = ["head", "eyes", "antenna", "body", "core",
              "arm_left", "arm_right", "leg_left", "leg_right", "wheels"]

PART_NAMES = {
    "head": "Head", "eyes": "Eyes", "antenna": "Antenna", "body": "Body",
    "core": "Battery Core", "arm_left": "Left Arm", "arm_right": "Right Arm",
    "leg_left": "Left Leg", "leg_right": "Right Leg", "wheels": "Wheels",
}

# ---- Puzzles -----------------------------------------------------------------
# Each puzzle drops ONE distinct part the first time it is cleared.
# 10 puzzles x 1 part = a robot that can always be completed, with no duplicates.
PUZZLES = {
    "memory":   dict(name="Memory Cards",   part="head",      color=C_RED,
                     coins=dict(easy=40, medium=90,  hard=160),
                     blurb="Flip cards and find the matching pairs."),
    "math":     dict(name="Quick Math",     part="eyes",      color=C_BLUE,
                     coins=dict(easy=35, medium=80,  hard=150),
                     blurb="Solve as many sums as you can before time runs out."),
    "sequence": dict(name="Sequence Recall", part="antenna",  color=C_PURPLE,
                     coins=dict(easy=45, medium=95,  hard=170),
                     blurb="Watch the lights flash, then repeat the order."),
    "sorting":  dict(name="Number Sort",    part="body",      color=C_GREEN,
                     coins=dict(easy=30, medium=75,  hard=140),
                     blurb="Click the numbers in ascending order."),
    "pattern":  dict(name="Pattern Match",  part="core",      color=C_ORANGE,
                     coins=dict(easy=40, medium=90,  hard=165),
                     blurb="Work out which shape continues the pattern."),
    "word":     dict(name="Word Puzzle",    part="arm_left",  color=C_PINK,
                     coins=dict(easy=40, medium=85,  hard=155),
                     blurb="Unscramble the village word, letter by letter."),
    "logic":    dict(name="Odd One Out",    part="arm_right", color=C_GOLD,
                     coins=dict(easy=35, medium=80,  hard=150),
                     blurb="Spot the item that does not belong."),
    "colours":  dict(name="Shape & Colour", part="leg_left",  color=C_BLUE,
                     coins=dict(easy=35, medium=85,  hard=155),
                     blurb="Tap every tile matching the target shape and colour."),
    "matching": dict(name="Matching Game",  part="leg_right", color=C_PURPLE,
                     coins=dict(easy=40, medium=90,  hard=160),
                     blurb="Pair each number with the word that names it."),
    "maze":     dict(name="Maze Escape",    part="wheels",    color=C_GREEN,
                     coins=dict(easy=50, medium=100, hard=180),
                     blurb="Steer the robot to the flag with the arrow keys."),
}
PUZZLE_IDS = list(PUZZLES.keys())

# ---- Buildings ---------------------------------------------------------------
# unlock: ("start",) | ("pop", N) | ("level", N) | ("robot",)
BUILDINGS = {
    "house_s":  dict(name="Small House",   zone="residential", cost=150,  pop=2, happy=2,  income=0,  unlock=("start",)),
    "house_m":  dict(name="Medium House",  zone="residential", cost=320,  pop=4, happy=3,  income=0,  unlock=("pop", 6)),
    "house_l":  dict(name="Large House",   zone="residential", cost=650,  pop=6, happy=4,  income=0,  unlock=("pop", 20)),
    "tree":     dict(name="Tree",          zone="nature",      cost=25,   pop=0, happy=1,  income=0,  unlock=("start",)),
    "road":     dict(name="Road",          zone="nature",      cost=15,   pop=0, happy=1,  income=0,  unlock=("start",)),
    "well":     dict(name="Water Well",    zone="nature",      cost=120,  pop=0, happy=3,  income=0,  unlock=("start",)),
    "field":    dict(name="Crop Field",    zone="farming",     cost=90,   pop=0, happy=1,  income=0,  unlock=("start",)),
    "cowshed":  dict(name="Cow Shed",      zone="farming",     cost=420,  pop=1, happy=3,  income=6,  unlock=("pop", 8)),
    "coop":     dict(name="Chicken Coop",  zone="farming",     cost=300,  pop=1, happy=2,  income=4,  unlock=("pop", 8)),
    "grocery":  dict(name="Grocery Shop",  zone="commercial",  cost=400,  pop=0, happy=5,  income=8,  unlock=("pop", 10)),
    "bakery":   dict(name="Bakery",        zone="commercial",  cost=700,  pop=0, happy=6,  income=12, unlock=("pop", 18)),
    "market":   dict(name="Market",        zone="commercial",  cost=2500, pop=0, happy=10, income=30, unlock=("pop", 100)),
    "school":   dict(name="School",        zone="community",   cost=800,  pop=0, happy=10, income=0,  unlock=("pop", 25)),
    "clinic":   dict(name="Clinic",        zone="community",   cost=1500, pop=0, happy=12, income=0,  unlock=("pop", 50)),
    "park":     dict(name="Park",          zone="community",   cost=260,  pop=0, happy=8,  income=0,  unlock=("pop", 6)),
    "play":     dict(name="Playground",    zone="community",   cost=380,  pop=0, happy=7,  income=0,  unlock=("pop", 15)),
    "hall":     dict(name="Town Hall",     zone="community",   cost=3200, pop=0, happy=14, income=20, unlock=("pop", 120)),
    "workshop": dict(name="Workshop",      zone="industrial",  cost=900,  pop=0, happy=-2, income=18, unlock=("robot",)),
    "power":    dict(name="Power Station", zone="industrial",  cost=2200, pop=0, happy=-4, income=26, unlock=("pop", 60)),
    "factory":  dict(name="Small Factory", zone="industrial",  cost=5000, pop=0, happy=-6, income=60, unlock=("pop", 200)),
}
ZONES = ["residential", "farming", "commercial", "community", "nature", "industrial"]
ZONE_LABEL = {"residential": "Housing", "farming": "Farming", "commercial": "Shops",
              "community": "Community", "nature": "Nature", "industrial": "Industry"}

# ---- Crops -------------------------------------------------------------------
CROPS = {
    "wheat":  dict(name="Wheat",  cost=20, grow=20, sell=55,  xp=5,  color=C_GOLD),
    "corn":   dict(name="Corn",   cost=35, grow=35, sell=95,  xp=8,  color=(230, 208, 90)),
    "carrot": dict(name="Carrot", cost=45, grow=50, sell=130, xp=10, color=C_ORANGE),
    "tomato": dict(name="Tomato", cost=60, grow=70, sell=180, xp=13, color=C_RED),
    "potato": dict(name="Potato", cost=80, grow=95, sell=250, xp=16, color=(190, 156, 110)),
    "rice":   dict(name="Rice",   cost=110, grow=130, sell=360, xp=20, color=(226, 226, 208)),
}

# ---- Robot upgrades ----------------------------------------------------------
ROBOT_UPGRADES = {
    1: dict(cost=0,    perk="Basic helper - gives one free hint in every puzzle."),
    2: dict(cost=500,  perk="Green thumb - crops grow 20% faster."),
    3: dict(cost=1200, perk="Builder - all buildings cost 10% less."),
    4: dict(cost=2500, perk="Harvester - automatically collects ready crops."),
    5: dict(cost=5000, perk="Automation - passive income and +5 happiness."),
}

# ---- Missions ----------------------------------------------------------------
# goal keys are read straight off the engine's stats, so adding a mission is
# a one-line change here.
MISSIONS = [
    dict(id="m1", text="Complete 3 puzzles",           stat="puzzles_solved", target=3,   reward=100),
    dict(id="m2", text="Collect 5 robot parts",        stat="parts",          target=5,   reward=250),
    dict(id="m3", text="Build 5 houses",               stat="houses",         target=5,   reward=300),
    dict(id="m4", text="Harvest 10 crops",             stat="crops_harvested", target=10, reward=200),
    dict(id="m5", text="Reach a population of 25",     stat="population",     target=25,  reward=400),
    dict(id="m6", text="Assemble the complete robot",  stat="parts",          target=10,  reward=750),
    dict(id="m7", text="Reach a population of 50",     stat="population",     target=50,  reward=900),
    dict(id="m8", text="Keep happiness above 80%",     stat="happiness",      target=80,  reward=350),
]

ACHIEVEMENTS = [
    dict(id="a1", name="First Puzzle",    stat="puzzles_solved",  target=1),
    dict(id="a2", name="First House",     stat="houses",          target=1),
    dict(id="a3", name="First Farm",      stat="fields",          target=1),
    dict(id="a4", name="Robot Builder",   stat="parts",           target=10),
    dict(id="a5", name="Village Founder", stat="population",      target=10),
    dict(id="a6", name="Farmer",          stat="crops_harvested", target=25),
    dict(id="a7", name="Big Town",        stat="population",      target=100),
    dict(id="a8", name="Puzzle Master",   stat="puzzles_solved",  target=30),
]


# ==============================================================================
# SECTION 3 - GAME ENGINE
# Everything about *rules* lives here. It never draws and never reads events,
# which is what makes it easy to test and easy to explain in a presentation.
# ==============================================================================

class Game:
    """The single source of truth for the whole game."""

    # -------------------------------------------------- creation ------------
    def __init__(self):
        self.new_game()

    def new_game(self):
        self.coins = 120            # small gift so the first puzzle isn't the only option
        self.xp = 0
        self.level = 1
        self.crops_stock = 0

        self.buildings = []         # [{bid, x, y, crop, planted}]
        self.parts = {p: False for p in PART_ORDER}
        self.robot_level = 1
        self.robot_pos = [GRID_W // 2, GRID_H // 2]

        self.puzzle_clears = {}     # pid -> times cleared
        self.best_scores = {}       # pid -> best score
        self.unlocked_difficulty = "easy"

        self.missions_done = []
        self.missions_claimed = []
        self.achievements = []

        self.stats = dict(puzzles_solved=0, coins_earned=0, coins_spent=0,
                          buildings_built=0, crops_harvested=0, robot_tasks=0)

        self.last_income = time.time()
        self.created = time.time()

    # -------------------------------------------------- derived values ------
    @property
    def population(self):
        """Recomputed from the buildings list, so it can never drift."""
        return sum(BUILDINGS[b["bid"]]["pop"] for b in self.buildings)

    @property
    def houses(self):
        return sum(1 for b in self.buildings if BUILDINGS[b["bid"]]["zone"] == "residential")

    @property
    def fields(self):
        return [b for b in self.buildings if b["bid"] == "field"]

    @property
    def part_count(self):
        return sum(1 for v in self.parts.values() if v)

    @property
    def robot_assembled(self):
        return self.part_count >= len(PART_ORDER)

    @property
    def happiness(self):
        """0-100. Parks and services push it up, industry and crowding pull it down."""
        h = 50
        h += sum(BUILDINGS[b["bid"]]["happy"] for b in self.buildings)
        pop = self.population
        if pop > 0:
            # each house should comfortably hold its residents
            if self.houses * 6 < pop:
                h -= 10
            if self.crops_stock * 4 < pop:
                h -= 8
            else:
                h += 5
        if self.robot_assembled and self.robot_level >= 5:
            h += 5
        return max(0, min(100, int(h)))

    @property
    def xp_to_next(self):
        return 100 + (self.level - 1) * 80

    def income_per_minute(self):
        base = sum(BUILDINGS[b["bid"]]["income"] for b in self.buildings)
        if self.robot_assembled and self.robot_level >= 5:
            base += 10
        return int(base * (0.5 + self.happiness / 100.0))

    # -------------------------------------------------- economy -------------
    def can_afford(self, amount):
        return self.coins >= amount

    def earn(self, amount):
        amount = int(amount)
        self.coins += amount
        self.stats["coins_earned"] += amount

    def spend(self, amount):
        amount = int(amount)
        if self.coins < amount:
            return False
        self.coins -= amount
        self.stats["coins_spent"] += amount
        return True

    def add_xp(self, amount):
        self.xp += amount
        levelled = []
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            levelled.append(self.level)
        return levelled

    # -------------------------------------------------- buildings -----------
    def building_cost(self, bid):
        cost = BUILDINGS[bid]["cost"]
        if self.robot_assembled and self.robot_level >= 3:
            cost = int(cost * 0.9)          # robot level 3 perk
        return cost

    def is_unlocked(self, bid):
        rule = BUILDINGS[bid]["unlock"]
        if rule[0] == "start":
            return True
        if rule[0] == "pop":
            return self.population >= rule[1]
        if rule[0] == "level":
            return self.level >= rule[1]
        if rule[0] == "robot":
            return self.robot_assembled
        return False

    def unlock_text(self, bid):
        rule = BUILDINGS[bid]["unlock"]
        if rule[0] == "pop":
            return "Needs %d population" % rule[1]
        if rule[0] == "level":
            return "Needs level %d" % rule[1]
        if rule[0] == "robot":
            return "Needs the assembled robot"
        return ""

    def tile_free(self, x, y):
        if not (0 <= x < GRID_W and 0 <= y < GRID_H):
            return False
        return all(not (b["x"] == x and b["y"] == y) for b in self.buildings)

    def building_at(self, x, y):
        for b in self.buildings:
            if b["x"] == x and b["y"] == y:
                return b
        return None

    def build(self, bid, x, y):
        """Returns (ok, message)."""
        if not self.is_unlocked(bid):
            return False, "That building is still locked."
        if not self.tile_free(x, y):
            return False, "That tile is already taken."
        cost = self.building_cost(bid)
        if not self.spend(cost):
            return False, "Not enough coins."
        entry = dict(bid=bid, x=x, y=y, crop=None, planted=0.0)
        self.buildings.append(entry)
        self.stats["buildings_built"] += 1
        self.add_xp(8)
        return True, "%s built!" % BUILDINGS[bid]["name"]

    def demolish(self, x, y):
        b = self.building_at(x, y)
        if not b:
            return False, "Nothing here."
        self.buildings.remove(b)
        self.earn(int(self.building_cost(b["bid"]) * 0.4))
        return True, "%s removed (40%% refunded)." % BUILDINGS[b["bid"]]["name"]

    def newly_unlocked(self, before_pop, before_level, before_robot):
        """Compares a 'before' snapshot with now and reports fresh unlocks."""
        out = []
        for bid, d in BUILDINGS.items():
            rule = d["unlock"]
            was = False
            if rule[0] == "start":
                was = True
            elif rule[0] == "pop":
                was = before_pop >= rule[1]
            elif rule[0] == "level":
                was = before_level >= rule[1]
            elif rule[0] == "robot":
                was = before_robot
            if self.is_unlocked(bid) and not was:
                out.append(bid)
        return out

    # -------------------------------------------------- farming -------------
    def grow_time(self, crop_id):
        t = CROPS[crop_id]["grow"]
        if self.robot_assembled and self.robot_level >= 2:
            t *= 0.8                       # robot level 2 perk
        return t

    def field_state(self, field):
        if not field["crop"]:
            return "empty"
        elapsed = time.time() - field["planted"]
        return "ready" if elapsed >= self.grow_time(field["crop"]) else "growing"

    def field_progress(self, field):
        if not field["crop"]:
            return 0.0
        elapsed = time.time() - field["planted"]
        return max(0.0, min(1.0, elapsed / self.grow_time(field["crop"])))

    def plant(self, field, crop_id):
        if field["crop"]:
            return False, "This field is already planted."
        if not self.spend(CROPS[crop_id]["cost"]):
            return False, "Not enough coins for seeds."
        field["crop"] = crop_id
        field["planted"] = time.time()
        return True, "%s planted." % CROPS[crop_id]["name"]

    def harvest(self, field):
        if self.field_state(field) != "ready":
            return False, "Not ready yet."
        crop = CROPS[field["crop"]]
        self.earn(crop["sell"])
        self.add_xp(crop["xp"])
        self.crops_stock += 1
        self.stats["crops_harvested"] += 1
        field["crop"] = None
        field["planted"] = 0.0
        return True, "Harvested %s for %d coins!" % (crop["name"], crop["sell"])

    def harvest_all(self):
        got = 0
        for f in self.fields:
            if self.field_state(f) == "ready":
                self.harvest(f)
                got += 1
        return got

    # -------------------------------------------------- robot ---------------
    def award_part(self, part_id):
        if self.parts.get(part_id):
            return False
        self.parts[part_id] = True
        return True

    def upgrade_robot(self):
        nxt = self.robot_level + 1
        if nxt not in ROBOT_UPGRADES:
            return False, "The robot is fully upgraded."
        if not self.robot_assembled:
            return False, "Assemble the robot first."
        cost = ROBOT_UPGRADES[nxt]["cost"]
        if not self.spend(cost):
            return False, "Need %d coins for this upgrade." % cost
        self.robot_level = nxt
        return True, "Robot upgraded to level %d!" % nxt

    # -------------------------------------------------- puzzles -------------
    def puzzle_reward(self, pid, difficulty, score):
        """score is 0-100. Returns a dict describing the payout."""
        meta = PUZZLES[pid]
        base = meta["coins"][difficulty]
        coins = int(round(base * (0.6 + 0.4 * (score / 100.0))))
        first = self.puzzle_clears.get(pid, 0) == 0
        return dict(coins=coins, xp=DIFF_XP[difficulty],
                    part=meta["part"] if first else None, first=first)

    def complete_puzzle(self, pid, difficulty, score):
        reward = self.puzzle_reward(pid, difficulty, score)
        self.earn(reward["coins"])
        reward["levels"] = self.add_xp(reward["xp"])
        if reward["part"]:
            self.award_part(reward["part"])
        self.puzzle_clears[pid] = self.puzzle_clears.get(pid, 0) + 1
        self.best_scores[pid] = max(self.best_scores.get(pid, 0), score)
        self.stats["puzzles_solved"] += 1
        # difficulty ladder
        if self.stats["puzzles_solved"] >= 5 and self.unlocked_difficulty == "easy":
            self.unlocked_difficulty = "medium"
        if self.stats["puzzles_solved"] >= 14 and self.unlocked_difficulty == "medium":
            self.unlocked_difficulty = "hard"
        return reward

    def difficulty_unlocked(self, difficulty):
        return DIFFICULTIES.index(difficulty) <= DIFFICULTIES.index(self.unlocked_difficulty)

    # -------------------------------------------------- missions ------------
    def stat_value(self, key):
        table = {
            "puzzles_solved": self.stats["puzzles_solved"],
            "parts": self.part_count,
            "houses": self.houses,
            "fields": len(self.fields),
            "crops_harvested": self.stats["crops_harvested"],
            "population": self.population,
            "happiness": self.happiness,
        }
        return table.get(key, 0)

    def mission_progress(self, m):
        return min(self.stat_value(m["stat"]), m["target"])

    def refresh_goals(self):
        """Marks newly completed missions/achievements. Returns notifications."""
        notes = []
        for m in MISSIONS:
            if m["id"] in self.missions_done:
                continue
            if self.stat_value(m["stat"]) >= m["target"]:
                self.missions_done.append(m["id"])
                notes.append(("mission", m["text"]))
        for a in ACHIEVEMENTS:
            if a["id"] in self.achievements:
                continue
            if self.stat_value(a["stat"]) >= a["target"]:
                self.achievements.append(a["id"])
                notes.append(("achievement", a["name"]))
        return notes

    def claim_mission(self, mid):
        if mid in self.missions_claimed or mid not in self.missions_done:
            return False, ""
        m = next(x for x in MISSIONS if x["id"] == mid)
        self.missions_claimed.append(mid)
        self.earn(m["reward"])
        return True, "Mission reward: +%d coins" % m["reward"]

    # -------------------------------------------------- objective -----------
    def next_objective(self):
        """First matching rule wins - this is what keeps the player guided."""
        if self.stats["puzzles_solved"] == 0:
            return "Open PUZZLES and solve your first challenge to earn coins and a robot part."
        if not self.buildings:
            return "Open BUILD and place your first Small House (150 coins)."
        if not self.fields:
            return "Build a Crop Field, then visit FARM to plant your first crop."
        if not self.robot_assembled:
            missing = len(PART_ORDER) - self.part_count
            return "Collect %d more robot part%s - each puzzle drops a new one." % (
                missing, "" if missing == 1 else "s")
        if self.happiness < 60:
            return "Happiness is low (%d%%). Build a Park or more housing." % self.happiness
        for bid in ["grocery", "school", "clinic", "market", "factory"]:
            rule = BUILDINGS[bid]["unlock"]
            if rule[0] == "pop" and self.population < rule[1]:
                return "Reach %d population to unlock the %s." % (rule[1], BUILDINGS[bid]["name"])
        if self.robot_level < 5:
            cost = ROBOT_UPGRADES[self.robot_level + 1]["cost"]
            return "Save %d coins to upgrade your robot to level %d." % (cost, self.robot_level + 1)
        return "Your township is thriving - keep expanding!"

    # -------------------------------------------------- per-second tick -----
    def tick(self):
        """Called about once a second by the app loop."""
        notes = []
        now = time.time()
        if now - self.last_income >= 60:
            self.last_income = now
            inc = self.income_per_minute()
            if inc:
                self.earn(inc)
                notes.append("Township income: +%d coins" % inc)
        # robot level 4 auto-harvest
        if self.robot_assembled and self.robot_level >= 4:
            got = self.harvest_all()
            if got:
                self.stats["robot_tasks"] += got
                notes.append("Robot harvested %d field%s" % (got, "" if got == 1 else "s"))
        return notes

    # -------------------------------------------------- save / load ---------
    def to_dict(self):
        return dict(
            version=SAVE_VERSION, coins=self.coins, xp=self.xp, level=self.level,
            crops_stock=self.crops_stock, buildings=self.buildings, parts=self.parts,
            robot_level=self.robot_level, robot_pos=self.robot_pos,
            puzzle_clears=self.puzzle_clears, best_scores=self.best_scores,
            unlocked_difficulty=self.unlocked_difficulty,
            missions_done=self.missions_done, missions_claimed=self.missions_claimed,
            achievements=self.achievements, stats=self.stats, created=self.created,
        )

    def load_dict(self, d):
        if d.get("version") != SAVE_VERSION:
            return False
        self.coins = d["coins"]
        self.xp = d["xp"]
        self.level = d["level"]
        self.crops_stock = d.get("crops_stock", 0)
        self.buildings = d["buildings"]
        self.parts = {p: bool(d["parts"].get(p)) for p in PART_ORDER}
        self.robot_level = d["robot_level"]
        self.robot_pos = d.get("robot_pos", [GRID_W // 2, GRID_H // 2])
        self.puzzle_clears = d.get("puzzle_clears", {})
        self.best_scores = d.get("best_scores", {})
        self.unlocked_difficulty = d.get("unlocked_difficulty", "easy")
        self.missions_done = d.get("missions_done", [])
        self.missions_claimed = d.get("missions_claimed", [])
        self.achievements = d.get("achievements", [])
        self.stats.update(d.get("stats", {}))
        self.created = d.get("created", time.time())
        self.last_income = time.time()
        return True


# ==============================================================================
# SECTION 4 - SAVE / LOAD (swap these two functions for a database later)
# ==============================================================================

def save_game(game):
    try:
        with open(SAVE_FILE, "w") as fh:
            json.dump(game.to_dict(), fh)
        return True
    except OSError:
        return False


def load_game(game):
    if not os.path.exists(SAVE_FILE):
        return False
    try:
        with open(SAVE_FILE) as fh:
            return game.load_dict(json.load(fh))
    except (OSError, ValueError, KeyError):
        return False


# ==============================================================================
# SECTION 5 - UI TOOLKIT
# Small reusable pieces. Every screen is built out of these.
# ==============================================================================

FONTS = {}


def init_fonts():
    def mk(size, bold=False):
        try:
            return pygame.font.SysFont("verdana,dejavusans,arial", size, bold=bold)
        except Exception:
            return pygame.font.Font(None, size + 4)
    FONTS["tiny"] = mk(12)
    FONTS["small"] = mk(14)
    FONTS["body"] = mk(16)
    FONTS["bodyb"] = mk(16, True)
    FONTS["mid"] = mk(20, True)
    FONTS["big"] = mk(28, True)
    FONTS["huge"] = mk(44, True)


def text(surf, msg, pos, font="body", color=C_INK, center=False, right=False):
    img = FONTS[font].render(str(msg), True, color)
    rect = img.get_rect()
    if center:
        rect.center = pos
    elif right:
        rect.midright = pos
    else:
        rect.topleft = pos
    surf.blit(img, rect)
    return rect


def panel(surf, rect, color=C_PANEL, radius=12, border=None, width=2):
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, rect, width, border_radius=radius)


def progress_bar(surf, rect, frac, color=C_GREEN, bg=C_PANEL_DARK):
    panel(surf, rect, bg, radius=rect.height // 2)
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        inner = pygame.Rect(rect.x, rect.y, max(rect.height, int(rect.w * frac)), rect.h)
        panel(surf, inner, color, radius=rect.height // 2)


class Button:
    """Click-me rectangle. Call draw() every frame and hit() on a click event."""

    def __init__(self, rect, label, color=C_GREEN, font="body", enabled=True, tag=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.color = color
        self.font = font
        self.enabled = enabled
        self.tag = tag

    def draw(self, surf, mouse):
        hover = self.enabled and self.rect.collidepoint(mouse)
        col = self.color if self.enabled else C_LOCK
        if hover:
            col = tuple(min(255, c + 22) for c in col)
        shadow = pygame.Rect(self.rect.x, self.rect.y + 3, self.rect.w, self.rect.h)
        panel(surf, shadow, tuple(max(0, c - 55) for c in col), radius=10)
        panel(surf, self.rect, col, radius=10)
        lbl_col = C_WHITE if sum(col) < 560 else C_INK
        text(surf, self.label, self.rect.center, self.font, lbl_col, center=True)

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


class Toasts:
    """Little messages that float up and fade - coins, unlocks, mission clears."""

    def __init__(self):
        self.items = []

    def push(self, msg, color=C_INK):
        self.items.append([msg, color, time.time()])
        self.items = self.items[-6:]

    def draw(self, surf):
        now = time.time()
        self.items = [t for t in self.items if now - t[2] < 3.4]
        for i, (msg, color, born) in enumerate(reversed(self.items)):
            age = now - born
            alpha = 255 if age < 2.4 else int(255 * (1 - (age - 2.4) / 1.0))
            y = SCREEN_H - NAV_H - 52 - i * 40 - int(min(age, 0.4) * 30)
            img = FONTS["bodyb"].render(msg, True, color)
            box = pygame.Surface((img.get_width() + 28, 34), pygame.SRCALPHA)
            pygame.draw.rect(box, (255, 252, 244, max(0, min(245, alpha))),
                             box.get_rect(), border_radius=17)
            pygame.draw.rect(box, (0, 0, 0, max(0, min(60, alpha))),
                             box.get_rect(), 2, border_radius=17)
            img.set_alpha(max(0, min(255, alpha)))
            box.blit(img, (14, 8))
            surf.blit(box, (SCREEN_W // 2 - box.get_width() // 2, y))


# ------------------------------------------------------------------ sprites --
# Buildings are drawn with plain shapes so the game needs no image files at all.

def _roof(surf, x, y, w, h, color):
    pygame.draw.polygon(surf, color, [(x, y + h), (x + w // 2, y), (x + w, y + h)])


def draw_building(surf, bid, rect, t=0.0):
    """Draw one building inside `rect` (a tile). `t` is a time value for wobble."""
    x, y, w, h = rect
    cx, cy = x + w // 2, y + h // 2
    b = BUILDINGS[bid]
    z = b["zone"]

    if bid == "road":
        pygame.draw.rect(surf, C_ROAD, rect)
        pygame.draw.line(surf, (226, 224, 216), (x + 6, cy), (x + w - 6, cy), 3)
        return
    if bid == "tree":
        pygame.draw.rect(surf, (128, 92, 60), (cx - 3, cy + 4, 6, h // 3))
        sway = math.sin(t * 2 + x) * 2
        pygame.draw.circle(surf, C_GREEN_DARK, (int(cx + sway), cy - 2), w // 3)
        pygame.draw.circle(surf, C_GREEN, (int(cx + sway) - 3, cy - 6), w // 4)
        return
    if bid == "well":
        pygame.draw.circle(surf, (150, 146, 140), (cx, cy + 6), w // 3)
        pygame.draw.circle(surf, C_WATER, (cx, cy + 6), w // 4)
        pygame.draw.rect(surf, (128, 92, 60), (cx - w // 3, cy - 12, 4, 20))
        pygame.draw.rect(surf, (128, 92, 60), (cx + w // 3 - 4, cy - 12, 4, 20))
        _roof(surf, x + 6, y + 4, w - 12, 12, C_RED)
        return
    if bid == "park":
        pygame.draw.circle(surf, C_GRASS_HL, (cx, cy), w // 2 - 3)
        pygame.draw.circle(surf, C_GREEN_DARK, (cx - 10, cy - 6), 8)
        pygame.draw.circle(surf, C_GREEN_DARK, (cx + 9, cy + 4), 7)
        pygame.draw.rect(surf, (128, 92, 60), (cx - 8, cy + 8, 16, 4))
        return
    if bid == "play":
        pygame.draw.rect(surf, C_GRASS_HL, (x + 4, y + 4, w - 8, h - 8), border_radius=6)
        pygame.draw.line(surf, C_RED, (x + 10, y + h - 10), (cx, y + 10), 4)
        pygame.draw.line(surf, C_BLUE, (x + w - 10, y + h - 10), (cx, y + 10), 4)
        pygame.draw.circle(surf, C_GOLD, (cx, y + 10), 5)
        return
    if bid == "field":
        return   # fields get their own renderer (crop stages)

    # --- generic building body -------------------------------------------
    body_col = {
        "residential": (244, 216, 176),
        "commercial": (208, 226, 244),
        "community": (226, 214, 244),
        "industrial": (214, 214, 214),
        "farming": (238, 220, 186),
    }.get(z, C_PANEL)
    roof_col = {
        "residential": C_RED,
        "commercial": C_BLUE,
        "community": C_PURPLE,
        "industrial": (110, 110, 118),
        "farming": (176, 112, 78),
    }.get(z, C_INK)

    size = {"house_s": 0.62, "house_m": 0.74, "house_l": 0.86}.get(bid, 0.80)
    bw = int(w * size)
    bh = int(h * size * 0.62)
    bx = cx - bw // 2
    by = y + h - bh - 6
    pygame.draw.ellipse(surf, (0, 0, 0, 30), (bx, y + h - 8, bw, 8))
    pygame.draw.rect(surf, body_col, (bx, by, bw, bh), border_radius=3)
    pygame.draw.rect(surf, C_INK_SOFT, (bx, by, bw, bh), 1, border_radius=3)
    _roof(surf, bx - 3, by - int(bh * 0.55), bw + 6, int(bh * 0.55) + 2, roof_col)

    # windows / details
    if z == "residential":
        pygame.draw.rect(surf, C_GOLD, (bx + 4, by + 5, 7, 7))
        pygame.draw.rect(surf, (140, 100, 62), (cx - 4, by + bh - 11, 8, 11))
    elif bid in ("power", "factory"):
        pygame.draw.rect(surf, (90, 90, 96), (bx + bw - 12, by - 20, 8, 22))
        puff = int(math.sin(t * 1.6 + x) * 3)
        pygame.draw.circle(surf, (228, 228, 230), (bx + bw - 8, by - 26 + puff), 5)
    elif bid in ("cowshed", "coop"):
        pygame.draw.rect(surf, C_WHITE, (bx + 5, by + 6, bw - 10, 6))
    else:
        for i in range(2):
            pygame.draw.rect(surf, C_WHITE, (bx + 5 + i * 13, by + 6, 9, 8))


def draw_field(surf, game, field, rect, t=0.0):
    x, y, w, h = rect
    pygame.draw.rect(surf, C_DIRT, rect, border_radius=4)
    for i in range(3):
        pygame.draw.line(surf, (176, 146, 102), (x + 5, y + 12 + i * 14), (x + w - 5, y + 12 + i * 14), 2)
    if not field["crop"]:
        return
    crop = CROPS[field["crop"]]
    state = game.field_state(field)
    prog = game.field_progress(field)
    height = int(6 + 20 * prog)
    for i in range(3):
        px = x + 12 + i * 16
        sway = math.sin(t * 3 + i + x) * (1.5 if state == "ready" else 0.6)
        pygame.draw.line(surf, C_GREEN_DARK, (px, y + h - 8),
                         (px + sway, y + h - 8 - height), 3)
        if prog > 0.45:
            pygame.draw.circle(surf, crop["color"],
                               (int(px + sway), y + h - 8 - height), 4 if state == "ready" else 3)
    if state == "ready":
        bob = math.sin(t * 5) * 2
        pygame.draw.circle(surf, C_GOLD, (x + w - 10, int(y + 10 + bob)), 6)
        pygame.draw.circle(surf, C_GOLD_DARK, (x + w - 10, int(y + 10 + bob)), 6, 2)
    else:
        progress_bar(surf, pygame.Rect(x + 6, y + h - 7, w - 12, 5), prog, C_GREEN)


def draw_robot(surf, cx, cy, scale=1.0, parts=None, t=0.0, ghost_missing=True):
    """Draws the robot. `parts` dict decides which pieces are solid vs outline."""
    if parts is None:
        parts = {p: True for p in PART_ORDER}
    s = scale
    bob = math.sin(t * 2.5) * 2 * s

    def col(part, solid, faded=(205, 205, 210)):
        return solid if parts.get(part) else faded

    def has(part):
        return parts.get(part) or ghost_missing

    # legs
    if has("leg_left"):
        pygame.draw.rect(surf, col("leg_left", (110, 118, 132)),
                         (cx - 14 * s, cy + 14 * s + bob, 8 * s, 18 * s), border_radius=int(3 * s))
    if has("leg_right"):
        pygame.draw.rect(surf, col("leg_right", (110, 118, 132)),
                         (cx + 6 * s, cy + 14 * s + bob, 8 * s, 18 * s), border_radius=int(3 * s))
    # wheels / feet
    if has("wheels"):
        pygame.draw.circle(surf, col("wheels", (72, 78, 90)),
                           (int(cx - 10 * s), int(cy + 34 * s + bob)), int(6 * s))
        pygame.draw.circle(surf, col("wheels", (72, 78, 90)),
                           (int(cx + 10 * s), int(cy + 34 * s + bob)), int(6 * s))
    # arms
    if has("arm_left"):
        pygame.draw.rect(surf, col("arm_left", (132, 140, 156)),
                         (cx - 30 * s, cy - 6 * s + bob, 9 * s, 24 * s), border_radius=int(4 * s))
    if has("arm_right"):
        pygame.draw.rect(surf, col("arm_right", (132, 140, 156)),
                         (cx + 21 * s, cy - 6 * s + bob, 9 * s, 24 * s), border_radius=int(4 * s))
    # body
    if has("body"):
        pygame.draw.rect(surf, col("body", (168, 176, 192)),
                         (cx - 21 * s, cy - 10 * s + bob, 42 * s, 30 * s), border_radius=int(7 * s))
    # core
    if has("core"):
        glow = 4 + math.sin(t * 4) * 1.5
        pygame.draw.circle(surf, col("core", C_GREEN),
                           (int(cx), int(cy + 5 * s + bob)), int((glow + 3) * s))
    # head
    if has("head"):
        pygame.draw.rect(surf, col("head", (196, 202, 216)),
                         (cx - 17 * s, cy - 36 * s + bob, 34 * s, 26 * s), border_radius=int(7 * s))
    # eyes
    if has("eyes"):
        ec = col("eyes", C_BLUE)
        pygame.draw.circle(surf, ec, (int(cx - 7 * s), int(cy - 24 * s + bob)), int(4 * s))
        pygame.draw.circle(surf, ec, (int(cx + 7 * s), int(cy - 24 * s + bob)), int(4 * s))
    # antenna
    if has("antenna"):
        ac = col("antenna", C_RED)
        pygame.draw.line(surf, (140, 146, 160), (cx, cy - 36 * s + bob), (cx, cy - 48 * s + bob), int(max(2, 3 * s)))
        pygame.draw.circle(surf, ac, (int(cx), int(cy - 50 * s + bob)), int(5 * s))


# ==============================================================================
# SECTION 6 - PUZZLE MINI-GAMES
# Every puzzle follows the SAME contract, which is why adding an 11th puzzle
# is one class plus one line in PUZZLE_CLASSES:
#
#     setup()                  build the level
#     handle(event, area)      react to a click or key
#     update(dt)               optional per-frame logic
#     draw(surface, area, t)   render inside the given rectangle
#     self.done / self.won / self.score(0-100)
# ==============================================================================

class Puzzle:
    def __init__(self, game, difficulty):
        self.game = game
        self.difficulty = difficulty
        self.d = DIFFICULTIES.index(difficulty)     # 0 easy, 1 medium, 2 hard
        self.done = False
        self.won = False
        self.score = 0
        self.objective = ""
        self.time_limit = 60
        self.hint_text = "Stay calm and look for the pattern."
        self.flash = None                            # (color, until) feedback
        self.setup()

    # -- helpers ----------------------------------------------------------
    def pick(self, easy, medium, hard):
        return [easy, medium, hard][self.d]

    def feedback(self, ok):
        self.flash = (C_GREEN if ok else C_RED, time.time() + 0.25)

    def finish(self, won, score):
        self.done = True
        self.won = won
        self.score = max(0, min(100, int(score)))

    def on_timeout(self):
        self.finish(False, 0)

    # -- overridable ------------------------------------------------------
    def setup(self): pass
    def handle(self, event, area): pass
    def update(self, dt): pass
    def draw(self, surf, area, t): pass

    # -- shared drawing ---------------------------------------------------
    def draw_flash(self, surf, area):
        if self.flash and time.time() < self.flash[1]:
            overlay = pygame.Surface((area.w, area.h), pygame.SRCALPHA)
            overlay.fill((*self.flash[0], 46))
            surf.blit(overlay, area.topleft)


def grid_rects(area, cols, rows, cell_w, cell_h, gap=12, top=0):
    """Centred grid of rects inside `area`."""
    total_w = cols * cell_w + (cols - 1) * gap
    total_h = rows * cell_h + (rows - 1) * gap
    ox = area.x + (area.w - total_w) // 2
    oy = area.y + top + (area.h - top - total_h) // 2
    return [pygame.Rect(ox + c * (cell_w + gap), oy + r * (cell_h + gap), cell_w, cell_h)
            for r in range(rows) for c in range(cols)]


# ------------------------------------------------------------- 1. memory -----
class MemoryPuzzle(Puzzle):
    def setup(self):
        self.objective = "Find every matching pair."
        cols, rows = self.pick((4, 2), (4, 3), (6, 3))
        self.cols, self.rows = cols, rows
        pairs = cols * rows // 2
        syms = list(range(pairs)) * 2
        random.shuffle(syms)
        self.cards = syms
        self.shown = [False] * len(syms)
        self.matched = [False] * len(syms)
        self.open = []
        self.moves = 0
        self.par = pairs * 2
        self.time_limit = self.pick(70, 90, 120)
        self.hint_text = "Say the positions out loud as you flip - it really helps."
        self.lock_until = 0

    def cell(self, area):
        return grid_rects(area, self.cols, self.rows, 92, 92, 14, 30)

    def handle(self, event, area):
        if event.type != pygame.MOUSEBUTTONDOWN or time.time() < self.lock_until:
            return
        for i, r in enumerate(self.cell(area)):
            if r.collidepoint(event.pos) and not self.matched[i] and not self.shown[i]:
                self.shown[i] = True
                self.open.append(i)
                if len(self.open) == 2:
                    self.moves += 1
                    a, b = self.open
                    if self.cards[a] == self.cards[b]:
                        self.matched[a] = self.matched[b] = True
                        self.open = []
                        self.feedback(True)
                        if all(self.matched):
                            eff = max(0.0, 1 - (self.moves - self.par / 2) / self.par)
                            self.finish(True, 55 + 45 * eff)
                    else:
                        self.feedback(False)
                        self.lock_until = time.time() + 0.6
                break

    def update(self, dt):
        if self.open and len(self.open) == 2 and time.time() >= self.lock_until:
            for i in self.open:
                self.shown[i] = False
            self.open = []

    def draw(self, surf, area, t):
        text(surf, "Moves: %d" % self.moves, (area.centerx, area.y + 14), "bodyb", C_INK_SOFT, center=True)
        for i, r in enumerate(self.cell(area)):
            if self.matched[i]:
                panel(surf, r, (216, 238, 216), border=C_GREEN)
            elif self.shown[i]:
                panel(surf, r, C_PANEL, border=C_INK_SOFT)
            else:
                panel(surf, r, C_BLUE, border=(60, 110, 180))
                pygame.draw.circle(surf, (120, 172, 234), r.center, 16, 4)
            if self.shown[i] or self.matched[i]:
                col = PUZZLE_COLORS[self.cards[i] % len(PUZZLE_COLORS)]
                shape = self.cards[i] % 3
                if shape == 0:
                    pygame.draw.circle(surf, col, r.center, 24)
                elif shape == 1:
                    pygame.draw.rect(surf, col, (r.centerx - 22, r.centery - 22, 44, 44), border_radius=6)
                else:
                    pygame.draw.polygon(surf, col, [(r.centerx, r.centery - 24),
                                                    (r.centerx - 24, r.centery + 20),
                                                    (r.centerx + 24, r.centery + 20)])
                text(surf, self.cards[i] + 1, (r.centerx, r.centery + 30), "tiny", C_INK, center=True)
        self.draw_flash(surf, area)


# --------------------------------------------------------------- 2. math -----
class MathPuzzle(Puzzle):
    def setup(self):
        self.objective = "Answer every sum correctly."
        self.total = self.pick(6, 8, 10)
        self.time_limit = self.pick(55, 70, 85)
        self.round = 0
        self.correct = 0
        self.hint_text = "Estimate first, then check the options against it."
        self.new_round()

    def new_round(self):
        hi = self.pick(12, 30, 60)
        ops = self.pick(["+", "-"], ["+", "-", "x"], ["+", "-", "x"])
        a, b = random.randint(2, hi), random.randint(2, hi)
        op = random.choice(ops)
        if op == "-" and b > a:
            a, b = b, a
        if op == "x":
            a, b = random.randint(2, self.pick(6, 9, 12)), random.randint(2, self.pick(6, 9, 12))
        self.q = "%d %s %d = ?" % (a, op, b)
        self.ans = {"+": a + b, "-": a - b, "x": a * b}[op]
        opts = {self.ans}
        while len(opts) < 4:
            opts.add(self.ans + random.choice([-9, -5, -3, -2, -1, 1, 2, 3, 5, 9, 11]))
        self.options = list(opts)
        random.shuffle(self.options)

    def handle(self, event, area):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for i, r in enumerate(grid_rects(area, 4, 1, 150, 78, 20, 110)):
            if r.collidepoint(event.pos):
                ok = self.options[i] == self.ans
                self.correct += 1 if ok else 0
                self.feedback(ok)
                self.round += 1
                if self.round >= self.total:
                    self.finish(self.correct >= max(1, int(self.total * 0.6)),
                                100 * self.correct / self.total)
                else:
                    self.new_round()
                break

    def draw(self, surf, area, t):
        text(surf, "Question %d / %d" % (self.round + 1, self.total),
             (area.centerx, area.y + 16), "bodyb", C_INK_SOFT, center=True)
        text(surf, self.q, (area.centerx, area.y + 78), "huge", C_INK, center=True)
        mouse = pygame.mouse.get_pos()
        for i, r in enumerate(grid_rects(area, 4, 1, 150, 78, 20, 110)):
            hover = r.collidepoint(mouse)
            panel(surf, r, C_PANEL if not hover else C_WHITE, border=C_BLUE, width=3)
            text(surf, self.options[i], r.center, "big", C_INK, center=True)
        self.draw_flash(surf, area)


# ----------------------------------------------------------- 3. sequence -----
class SequencePuzzle(Puzzle):
    def setup(self):
        self.objective = "Repeat the flashing order."
        self.length = self.pick(4, 6, 8)
        self.time_limit = self.pick(70, 85, 100)
        self.seq = [random.randrange(4) for _ in range(self.length)]
        self.input = []
        self.phase = "show"
        self.step = 0
        self.timer = 0.8
        self.lit = None
        self.hint_text = "Chunk the sequence into pairs - much easier to remember."

    def pads(self, area):
        return grid_rects(area, 2, 2, 150, 130, 22, 50)

    def update(self, dt):
        if self.phase != "show":
            return
        self.timer -= dt
        if self.timer <= 0:
            if self.lit is None:
                if self.step >= len(self.seq):
                    self.phase = "input"
                    return
                self.lit = self.seq[self.step]
                self.timer = 0.45
            else:
                self.lit = None
                self.step += 1
                self.timer = 0.22

    def handle(self, event, area):
        if self.phase != "input" or event.type != pygame.MOUSEBUTTONDOWN:
            return
        for i, r in enumerate(self.pads(area)):
            if r.collidepoint(event.pos):
                self.lit = i
                self.input.append(i)
                idx = len(self.input) - 1
                if self.seq[idx] != i:
                    self.feedback(False)
                    self.finish(False, 100 * idx / self.length)
                else:
                    self.feedback(True)
                    if len(self.input) == self.length:
                        self.finish(True, 100)
                break

    def draw(self, surf, area, t):
        msg = "Watch carefully..." if self.phase == "show" else \
              "Your turn:  %d / %d" % (len(self.input), self.length)
        text(surf, msg, (area.centerx, area.y + 18), "mid", C_INK_SOFT, center=True)
        cols = [C_RED, C_BLUE, C_GREEN, C_GOLD]
        for i, r in enumerate(self.pads(area)):
            c = cols[i]
            if self.lit == i:
                c = tuple(min(255, v + 70) for v in c)
            panel(surf, r, c, radius=16, border=tuple(max(0, v - 60) for v in cols[i]), width=4)
        self.draw_flash(surf, area)


# ------------------------------------------------------------ 4. sorting -----
class SortingPuzzle(Puzzle):
    def setup(self):
        self.objective = "Click the numbers from smallest to largest."
        n = self.pick(8, 12, 16)
        self.cols = self.pick(4, 4, 4)
        self.rows = n // self.cols
        self.numbers = random.sample(range(1, self.pick(40, 99, 200)), n)
        self.order = sorted(self.numbers)
        self.taken = []
        self.time_limit = self.pick(45, 60, 75)
        self.mistakes = 0
        self.hint_text = "Scan the whole board for the smallest number before clicking."

    def handle(self, event, area):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for i, r in enumerate(grid_rects(area, self.cols, self.rows, 108, 66, 16, 30)):
            if r.collidepoint(event.pos) and self.numbers[i] not in self.taken:
                if self.numbers[i] == self.order[len(self.taken)]:
                    self.taken.append(self.numbers[i])
                    self.feedback(True)
                    if len(self.taken) == len(self.order):
                        self.finish(True, max(35, 100 - self.mistakes * 12))
                else:
                    self.mistakes += 1
                    self.feedback(False)
                    if self.mistakes >= 4:
                        self.finish(False, 100 * len(self.taken) / len(self.order))
                break

    def draw(self, surf, area, t):
        nxt = self.order[len(self.taken)] if len(self.taken) < len(self.order) else "-"
        text(surf, "Next: %s      Mistakes: %d / 4" % (nxt if self.taken else "?", self.mistakes),
             (area.centerx, area.y + 16), "bodyb", C_INK_SOFT, center=True)
        for i, r in enumerate(grid_rects(area, self.cols, self.rows, 108, 66, 16, 30)):
            used = self.numbers[i] in self.taken
            panel(surf, r, (222, 240, 222) if used else C_PANEL,
                  border=C_GREEN if used else C_INK_SOFT, width=3 if used else 2)
            text(surf, self.numbers[i], r.center, "big",
                 C_INK_SOFT if used else C_INK, center=True)
        self.draw_flash(surf, area)


# ------------------------------------------------------------ 5. pattern -----
class PatternPuzzle(Puzzle):
    SHAPES = ["circle", "square", "triangle", "diamond"]

    def setup(self):
        self.objective = "Choose the shape that continues the pattern."
        self.total = self.pick(4, 5, 6)
        self.time_limit = self.pick(60, 75, 90)
        self.round = 0
        self.correct = 0
        self.hint_text = "Check colour and shape separately - they often repeat differently."
        self.new_round()

    def _item(self, i):
        return (self.SHAPES[self.shape_cycle[i % len(self.shape_cycle)]],
                PUZZLE_COLORS[self.color_cycle[i % len(self.color_cycle)]])

    def new_round(self):
        slen = self.pick(2, 2, 3)
        clen = self.pick(2, 3, 3)
        self.shape_cycle = [random.randrange(4) for _ in range(slen)]
        self.color_cycle = [random.randrange(len(PUZZLE_COLORS)) for _ in range(clen)]
        self.shown = self.pick(5, 6, 6)
        answer = self._item(self.shown)
        opts = {answer}
        while len(opts) < 4:
            opts.add((random.choice(self.SHAPES), random.choice(PUZZLE_COLORS)))
        self.options = list(opts)
        random.shuffle(self.options)
        self.answer = answer

    def handle(self, event, area):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for i, r in enumerate(grid_rects(area, 4, 1, 120, 100, 24, 160)):
            if r.collidepoint(event.pos):
                ok = self.options[i] == self.answer
                self.correct += 1 if ok else 0
                self.feedback(ok)
                self.round += 1
                if self.round >= self.total:
                    self.finish(self.correct >= max(1, int(self.total * 0.6)),
                                100 * self.correct / self.total)
                else:
                    self.new_round()
                break

    def _draw_shape(self, surf, kind, color, cx, cy, s=26):
        if kind == "circle":
            pygame.draw.circle(surf, color, (cx, cy), s)
        elif kind == "square":
            pygame.draw.rect(surf, color, (cx - s, cy - s, s * 2, s * 2), border_radius=5)
        elif kind == "triangle":
            pygame.draw.polygon(surf, color, [(cx, cy - s), (cx - s, cy + s), (cx + s, cy + s)])
        else:
            pygame.draw.polygon(surf, color, [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)])

    def draw(self, surf, area, t):
        text(surf, "Pattern %d / %d" % (self.round + 1, self.total),
             (area.centerx, area.y + 14), "bodyb", C_INK_SOFT, center=True)
        start_x = area.centerx - (self.shown * 100) // 2
        for i in range(self.shown):
            kind, col = self._item(i)
            self._draw_shape(surf, kind, col, start_x + i * 100 + 40, area.y + 90)
        qx = start_x + self.shown * 100 + 40
        panel(surf, pygame.Rect(qx - 32, area.y + 58, 64, 64), C_PANEL_DARK, border=C_INK_SOFT)
        text(surf, "?", (qx, area.y + 90), "big", C_INK, center=True)
        mouse = pygame.mouse.get_pos()
        for i, r in enumerate(grid_rects(area, 4, 1, 120, 100, 24, 160)):
            panel(surf, r, C_WHITE if r.collidepoint(mouse) else C_PANEL, border=C_ORANGE, width=3)
            kind, col = self.options[i]
            self._draw_shape(surf, kind, col, r.centerx, r.centery)
        self.draw_flash(surf, area)


# --------------------------------------------------------------- 6. word -----
WORD_BANK = [
    ("FARM", "Where crops are grown"), ("ROBOT", "Your metal helper"),
    ("HOUSE", "People live here"), ("WHEAT", "A golden crop"),
    ("SCHOOL", "Children learn here"), ("MARKET", "Where goods are sold"),
    ("GARDEN", "Full of flowers"), ("BAKERY", "Sells fresh bread"),
    ("VILLAGE", "A small township"), ("HARVEST", "Collecting ripe crops"),
    ("FACTORY", "Makes things at scale"), ("TRACTOR", "Pulls the plough"),
    ("CLINIC", "Where you see a doctor"), ("BRIDGE", "Crosses a river"),
]


class WordPuzzle(Puzzle):
    def setup(self):
        self.objective = "Unscramble the word by clicking letters in order."
        self.total = self.pick(3, 4, 5)
        self.time_limit = self.pick(60, 75, 90)
        self.round = 0
        self.correct = 0
        self.hint_text = "Start with the first letter of the clue's most obvious answer."
        self.new_round()

    def new_round(self):
        pool = [w for w in WORD_BANK if len(w[0]) <= self.pick(5, 6, 9)]
        self.word, self.clue = random.choice(pool or WORD_BANK)
        letters = list(self.word)
        random.shuffle(letters)
        self.letters = letters
        self.used = [False] * len(letters)
        self.built = ""

    def tiles(self, area):
        return grid_rects(area, len(self.letters), 1, 62, 70, 12, 170)

    def handle(self, event, area):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for i, r in enumerate(self.tiles(area)):
            if r.collidepoint(event.pos) and not self.used[i]:
                if self.letters[i] == self.word[len(self.built)]:
                    self.used[i] = True
                    self.built += self.letters[i]
                    self.feedback(True)
                    if self.built == self.word:
                        self.correct += 1
                        self.round += 1
                        if self.round >= self.total:
                            self.finish(self.correct >= max(1, self.total - 1),
                                        100 * self.correct / self.total)
                        else:
                            self.new_round()
                else:
                    self.feedback(False)
                break

    def draw(self, surf, area, t):
        text(surf, "Word %d / %d" % (self.round + 1, self.total),
             (area.centerx, area.y + 14), "bodyb", C_INK_SOFT, center=True)
        text(surf, "Clue:  %s" % self.clue, (area.centerx, area.y + 58), "mid", C_INK, center=True)
        slots = len(self.word)
        sx = area.centerx - slots * 34 // 2
        for i in range(slots):
            r = pygame.Rect(sx + i * 34, area.y + 96, 28, 42)
            panel(surf, r, C_PANEL_DARK, radius=6)
            if i < len(self.built):
                text(surf, self.built[i], r.center, "mid", C_INK, center=True)
        for i, r in enumerate(self.tiles(area)):
            if self.used[i]:
                panel(surf, r, C_PANEL_DARK, border=C_LOCK)
            else:
                panel(surf, r, C_PINK, border=(206, 106, 140), width=3)
                text(surf, self.letters[i], r.center, "big", C_WHITE, center=True)
        self.draw_flash(surf, area)


# -------------------------------------------------------------- 7. logic -----
class LogicPuzzle(Puzzle):
    def setup(self):
        self.objective = "Click the item that does not belong."
        self.total = self.pick(5, 6, 8)
        self.time_limit = self.pick(50, 65, 80)
        self.round = 0
        self.correct = 0
        self.hint_text = "Compare shape, then colour, then size - one of them is the odd one."
        self.new_round()

    def new_round(self):
        n = self.pick(4, 5, 6)
        shape = random.choice(PatternPuzzle.SHAPES)
        color = random.choice(PUZZLE_COLORS)
        self.items = [(shape, color, 26)] * n
        self.odd = random.randrange(n)
        mode = random.choice(["shape", "color", "size"] if self.d >= 1 else ["shape", "color"])
        if mode == "shape":
            other = random.choice([s for s in PatternPuzzle.SHAPES if s != shape])
            odd_item = (other, color, 26)
        elif mode == "color":
            other = random.choice([c for c in PUZZLE_COLORS if c != color])
            odd_item = (shape, other, 26)
        else:
            odd_item = (shape, color, 18)
        self.items = list(self.items)
        self.items[self.odd] = odd_item

    def handle(self, event, area):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for i, r in enumerate(grid_rects(area, len(self.items), 1, 110, 110, 20, 70)):
            if r.collidepoint(event.pos):
                ok = i == self.odd
                self.correct += 1 if ok else 0
                self.feedback(ok)
                self.round += 1
                if self.round >= self.total:
                    self.finish(self.correct >= max(1, int(self.total * 0.6)),
                                100 * self.correct / self.total)
                else:
                    self.new_round()
                break

    def draw(self, surf, area, t):
        text(surf, "Round %d / %d" % (self.round + 1, self.total),
             (area.centerx, area.y + 20), "bodyb", C_INK_SOFT, center=True)
        mouse = pygame.mouse.get_pos()
        for i, r in enumerate(grid_rects(area, len(self.items), 1, 110, 110, 20, 70)):
            panel(surf, r, C_WHITE if r.collidepoint(mouse) else C_PANEL, border=C_GOLD_DARK, width=3)
            kind, col, size = self.items[i]
            PatternPuzzle._draw_shape(self, surf, kind, col, r.centerx, r.centery, size)
        self.draw_flash(surf, area)


# ------------------------------------------------------------ 8. colours -----
class ColourPuzzle(Puzzle):
    def setup(self):
        self.objective = "Tap every tile that matches the target."
        cols, rows = self.pick((5, 3), (6, 3), (7, 4))
        self.cols, self.rows = cols, rows
        self.time_limit = self.pick(40, 50, 60)
        self.hint_text = "Sweep row by row instead of hunting randomly."
        self.t_shape = random.choice(PatternPuzzle.SHAPES)
        self.t_color = random.choice(PUZZLE_COLORS)
        n = cols * rows
        self.items = []
        targets = 0
        for _ in range(n):
            if random.random() < 0.3:
                self.items.append((self.t_shape, self.t_color))
                targets += 1
            else:
                s = random.choice(PatternPuzzle.SHAPES)
                c = random.choice(PUZZLE_COLORS)
                if (s, c) == (self.t_shape, self.t_color):
                    targets += 1
                self.items.append((s, c))
        if targets == 0:
            self.items[0] = (self.t_shape, self.t_color)
            targets = 1
        self.targets = targets
        self.found = set()
        self.mistakes = 0

    def handle(self, event, area):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for i, r in enumerate(grid_rects(area, self.cols, self.rows, 88, 76, 12, 70)):
            if r.collidepoint(event.pos) and i not in self.found:
                if self.items[i] == (self.t_shape, self.t_color):
                    self.found.add(i)
                    self.feedback(True)
                    if len(self.found) == self.targets:
                        self.finish(True, max(40, 100 - self.mistakes * 10))
                else:
                    self.mistakes += 1
                    self.feedback(False)
                    if self.mistakes >= 5:
                        self.finish(False, 100 * len(self.found) / self.targets)
                break

    def draw(self, surf, area, t):
        text(surf, "Find all:", (area.centerx - 90, area.y + 26), "mid", C_INK_SOFT, center=True)
        PatternPuzzle._draw_shape(self, surf, self.t_shape, self.t_color,
                                  area.centerx - 10, area.y + 26, 20)
        text(surf, "%d / %d found   Misses: %d / 5" % (len(self.found), self.targets, self.mistakes),
             (area.centerx + 130, area.y + 26), "bodyb", C_INK_SOFT, center=True)
        for i, r in enumerate(grid_rects(area, self.cols, self.rows, 88, 76, 12, 70)):
            hit = i in self.found
            panel(surf, r, (222, 240, 222) if hit else C_PANEL,
                  border=C_GREEN if hit else C_INK_SOFT, width=3 if hit else 2)
            kind, col = self.items[i]
            PatternPuzzle._draw_shape(self, surf, kind, col, r.centerx, r.centery, 22)
        self.draw_flash(surf, area)


# ----------------------------------------------------------- 9. matching -----
NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven",
                "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
                "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


class MatchingPuzzle(Puzzle):
    def setup(self):
        self.objective = "Match each number with the word that names it."
        n = self.pick(4, 5, 6)
        self.time_limit = self.pick(50, 65, 80)
        self.hint_text = "Do the ones you are sure about first - the rest narrow down."
        self.nums = random.sample(range(1, 21), n)
        self.left = list(self.nums)
        self.right = list(self.nums)
        random.shuffle(self.right)
        self.matched = set()
        self.sel = None
        self.mistakes = 0

    def _cols(self, area):
        n = len(self.left)
        h, gap = 62, 14
        top = area.y + (area.h - (n * h + (n - 1) * gap)) // 2 + 20
        lx = area.centerx - 250
        rx = area.centerx + 50
        L = [pygame.Rect(lx, top + i * (h + gap), 200, h) for i in range(n)]
        R = [pygame.Rect(rx, top + i * (h + gap), 200, h) for i in range(n)]
        return L, R

    def handle(self, event, area):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        L, R = self._cols(area)
        for i, r in enumerate(L):
            if r.collidepoint(event.pos) and self.left[i] not in self.matched:
                self.sel = i
                return
        for j, r in enumerate(R):
            if r.collidepoint(event.pos) and self.sel is not None and self.right[j] not in self.matched:
                if self.left[self.sel] == self.right[j]:
                    self.matched.add(self.right[j])
                    self.feedback(True)
                    self.sel = None
                    if len(self.matched) == len(self.left):
                        self.finish(True, max(40, 100 - self.mistakes * 12))
                else:
                    self.mistakes += 1
                    self.feedback(False)
                    self.sel = None
                    if self.mistakes >= 5:
                        self.finish(False, 100 * len(self.matched) / len(self.left))
                return

    def draw(self, surf, area, t):
        text(surf, "Matched %d / %d     Misses: %d / 5"
             % (len(self.matched), len(self.left), self.mistakes),
             (area.centerx, area.y + 20), "bodyb", C_INK_SOFT, center=True)
        L, R = self._cols(area)
        for i, r in enumerate(L):
            done = self.left[i] in self.matched
            col = (222, 240, 222) if done else (C_PURPLE if self.sel == i else C_PANEL)
            panel(surf, r, col, border=C_PURPLE, width=3)
            text(surf, self.left[i], r.center, "big",
                 C_WHITE if self.sel == i else C_INK, center=True)
        for j, r in enumerate(R):
            done = self.right[j] in self.matched
            panel(surf, r, (222, 240, 222) if done else C_PANEL, border=C_PURPLE, width=3)
            text(surf, NUMBER_WORDS[self.right[j]].title(), r.center, "mid", C_INK, center=True)
        self.draw_flash(surf, area)


# --------------------------------------------------------------- 10. maze ----
class MazePuzzle(Puzzle):
    def setup(self):
        self.objective = "Reach the flag using the arrow keys."
        self.w, self.h = self.pick((13, 9), (17, 11), (21, 13))
        self.time_limit = self.pick(60, 80, 100)
        self.hint_text = "Keep one hand on the wall - it always finds the exit."
        self.grid = self._generate(self.w, self.h)
        self.px, self.py = 1, 1
        self.goal = (self.w - 2, self.h - 2)
        self.steps = 0

    @staticmethod
    def _generate(w, h):
        g = [[1] * w for _ in range(h)]
        stack = [(1, 1)]
        g[1][1] = 0
        while stack:
            x, y = stack[-1]
            nb = []
            for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
                nx, ny = x + dx, y + dy
                if 1 <= nx < w - 1 and 1 <= ny < h - 1 and g[ny][nx] == 1:
                    nb.append((nx, ny, dx, dy))
            if not nb:
                stack.pop()
                continue
            nx, ny, dx, dy = random.choice(nb)
            g[y + dy // 2][x + dx // 2] = 0
            g[ny][nx] = 0
            stack.append((nx, ny))
        g[h - 2][w - 2] = 0
        return g

    def handle(self, event, area):
        if event.type != pygame.KEYDOWN:
            return
        moves = {pygame.K_UP: (0, -1), pygame.K_w: (0, -1),
                 pygame.K_DOWN: (0, 1), pygame.K_s: (0, 1),
                 pygame.K_LEFT: (-1, 0), pygame.K_a: (-1, 0),
                 pygame.K_RIGHT: (1, 0), pygame.K_d: (1, 0)}
        if event.key not in moves:
            return
        dx, dy = moves[event.key]
        nx, ny = self.px + dx, self.py + dy
        if 0 <= nx < self.w and 0 <= ny < self.h and self.grid[ny][nx] == 0:
            self.px, self.py = nx, ny
            self.steps += 1
            if (nx, ny) == self.goal:
                ideal = self.w + self.h
                self.finish(True, max(50, 100 - max(0, self.steps - ideal) // 2))

    def draw(self, surf, area, t):
        cell = min((area.w - 60) // self.w, (area.h - 70) // self.h)
        ox = area.centerx - self.w * cell // 2
        oy = area.y + 46
        text(surf, "Steps: %d" % self.steps, (area.centerx, area.y + 18), "bodyb", C_INK_SOFT, center=True)
        panel(surf, pygame.Rect(ox - 8, oy - 8, self.w * cell + 16, self.h * cell + 16), C_PANEL_DARK)
        for y in range(self.h):
            for x in range(self.w):
                r = pygame.Rect(ox + x * cell, oy + y * cell, cell, cell)
                pygame.draw.rect(surf, (96, 104, 120) if self.grid[y][x] else C_WHITE, r)
        gx, gy = self.goal
        pygame.draw.rect(surf, C_GREEN, (ox + gx * cell + 2, oy + gy * cell + 2, cell - 4, cell - 4))
        pygame.draw.circle(surf, C_BLUE,
                           (ox + self.px * cell + cell // 2, oy + self.py * cell + cell // 2),
                           max(3, cell // 2 - 3))
        self.draw_flash(surf, area)


PUZZLE_CLASSES = {
    "memory": MemoryPuzzle, "math": MathPuzzle, "sequence": SequencePuzzle,
    "sorting": SortingPuzzle, "pattern": PatternPuzzle, "word": WordPuzzle,
    "logic": LogicPuzzle, "colours": ColourPuzzle, "matching": MatchingPuzzle,
    "maze": MazePuzzle,
}


# ==============================================================================
# SECTION 7 - SCREENS
# Screens only read state and draw. All rule changes go through `self.game`.
# ==============================================================================

CONTENT = pygame.Rect(0, 112, SCREEN_W, SCREEN_H - 112 - NAV_H - 6)
PLAY_AREA = pygame.Rect(40, 200, SCREEN_W - 80, SCREEN_H - 200 - NAV_H - 30)
SIDE = pygame.Rect(MAP_X + GRID_W * TILE + 12, MAP_Y, SCREEN_W - (MAP_X + GRID_W * TILE) - 42, GRID_H * TILE)


class Screen:
    """Base screen. `app` gives access to the game, toasts and navigation."""

    def __init__(self, app):
        self.app = app
        self.game = app.game

    def handle(self, event): pass
    def update(self, dt): pass
    def draw(self, surf, t): pass


# ------------------------------------------------------------- MAP SCREEN ----
class MapScreen(Screen):
    def tile_at(self, pos):
        x = (pos[0] - MAP_X) // TILE
        y = (pos[1] - MAP_Y) // TILE
        if 0 <= x < GRID_W and 0 <= y < GRID_H:
            return int(x), int(y)
        return None

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.app.cancel_btn and self.app.cancel_btn.hit(event.pos):
                self.app.selected_build = None
                return
            cell = self.tile_at(event.pos)
            if not cell:
                return
            x, y = cell
            if event.button == 3:                       # right click = demolish
                ok, msg = self.game.demolish(x, y)
                self.app.notify(msg, C_RED if not ok else C_INK)
                self.app.after_change()
                return
            if self.app.selected_build:
                ok, msg = self.game.build(self.app.selected_build, x, y)
                self.app.notify(msg, C_INK if ok else C_RED)
                if ok:
                    self.app.after_change()
                    if not pygame.key.get_mods() & pygame.KMOD_SHIFT:
                        self.app.selected_build = None
                return
            b = self.game.building_at(x, y)
            if b and b["bid"] == "field":
                if self.game.field_state(b) == "ready":
                    ok, msg = self.game.harvest(b)
                    self.app.notify(msg, C_GREEN_DARK)
                    self.app.after_change()
                else:
                    self.app.goto("farm")
            elif b:
                self.app.notify("%s  -  +%d pop, %+d happiness" % (
                    BUILDINGS[b["bid"]]["name"], BUILDINGS[b["bid"]]["pop"],
                    BUILDINGS[b["bid"]]["happy"]))

    def draw(self, surf, t):
        g = self.game
        mouse = pygame.mouse.get_pos()
        # ground
        for y in range(GRID_H):
            for x in range(GRID_W):
                r = pygame.Rect(MAP_X + x * TILE, MAP_Y + y * TILE, TILE, TILE)
                pygame.draw.rect(surf, C_GRASS if (x + y) % 2 == 0 else C_GRASS_ALT, r)
        pygame.draw.rect(surf, (96, 150, 88),
                         (MAP_X - 3, MAP_Y - 3, GRID_W * TILE + 6, GRID_H * TILE + 6), 3,
                         border_radius=6)
        # buildings
        for b in sorted(g.buildings, key=lambda b: b["y"]):
            r = pygame.Rect(MAP_X + b["x"] * TILE, MAP_Y + b["y"] * TILE, TILE, TILE)
            if b["bid"] == "field":
                draw_field(surf, g, b, r, t)
            else:
                draw_building(surf, b["bid"], r, t)
        # robot walking around
        if g.robot_assembled:
            rx = MAP_X + (GRID_W * TILE) // 2 + math.sin(t * 0.5) * 140
            ry = MAP_Y + (GRID_H * TILE) // 2 + math.cos(t * 0.35) * 90
            draw_robot(surf, int(rx), int(ry), 0.62, g.parts, t)
        # placement preview
        cell = self.tile_at(mouse)
        if self.app.selected_build and cell:
            x, y = cell
            r = pygame.Rect(MAP_X + x * TILE, MAP_Y + y * TILE, TILE, TILE)
            ok = g.tile_free(x, y) and g.can_afford(g.building_cost(self.app.selected_build))
            ov = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            ov.fill((*(C_GREEN if ok else C_RED), 110))
            surf.blit(ov, r.topleft)
            if ok:
                draw_building(surf, self.app.selected_build, r, t)
        self.draw_side(surf, t)

    def draw_side(self, surf, t):
        g = self.game
        panel(surf, SIDE, C_PANEL, border=C_PANEL_DARK)
        x = SIDE.x + 16
        y = SIDE.y + 14
        text(surf, "TOWNSHIP", (x, y), "mid", C_INK); y += 34
        rows = [
            ("Level", "%d" % g.level),
            ("Houses", "%d" % g.houses),
            ("Fields", "%d" % len(g.fields)),
            ("Income", "%d /min" % g.income_per_minute()),
            ("Crops held", "%d" % g.crops_stock),
            ("Puzzles", "%d solved" % g.stats["puzzles_solved"]),
        ]
        for k, v in rows:
            text(surf, k, (x, y), "small", C_INK_SOFT)
            text(surf, v, (SIDE.right - 16, y + 8), "bodyb", C_INK, right=True)
            y += 26
        y += 6
        text(surf, "XP  %d / %d" % (g.xp, g.xp_to_next), (x, y), "small", C_INK_SOFT); y += 18
        progress_bar(surf, pygame.Rect(x, y, SIDE.w - 32, 10), g.xp / g.xp_to_next, C_PURPLE)
        y += 28

        if self.app.selected_build:
            bid = self.app.selected_build
            text(surf, "PLACING", (x, y), "small", C_INK_SOFT); y += 20
            text(surf, BUILDINGS[bid]["name"], (x, y), "bodyb", C_INK); y += 22
            text(surf, "%d coins  -  click a free tile" % g.building_cost(bid),
                 (x, y), "small", C_INK_SOFT); y += 24
            self.app.cancel_btn = Button((x, y, SIDE.w - 32, 34), "Cancel", C_RED)
            self.app.cancel_btn.draw(surf, pygame.mouse.get_pos())
            y += 44
        else:
            self.app.cancel_btn = None
            text(surf, "Right-click a building", (x, y), "small", C_INK_SOFT); y += 16
            text(surf, "to demolish it (40% back).", (x, y), "small", C_INK_SOFT); y += 26

        # robot corner
        text(surf, "ROBOT", (x, SIDE.bottom - 146), "mid", C_INK)
        draw_robot(surf, SIDE.centerx, SIDE.bottom - 72, 0.72, g.parts, t)
        label = ("Level %d" % g.robot_level) if g.robot_assembled else ("%d / 10 parts" % g.part_count)
        text(surf, label, (SIDE.centerx, SIDE.bottom - 14), "bodyb", C_INK_SOFT, center=True)


# ------------------------------------------------------- PUZZLE HUB SCREEN ---
class PuzzleHubScreen(Screen):
    def cards(self):
        return grid_rects(pygame.Rect(60, 180, SCREEN_W - 120, 420), 5, 2, 178, 178, 18, 0)

    def diff_buttons(self):
        out = []
        for i, d in enumerate(DIFFICULTIES):
            out.append(Button((SCREEN_W // 2 - 195 + i * 134, 132, 124, 36),
                              DIFF_LABEL[d], C_GREEN if self.game.difficulty_unlocked(d) else C_LOCK,
                              enabled=self.game.difficulty_unlocked(d), tag=d))
        return out

    def handle(self, event):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for b in self.diff_buttons():
            if b.hit(event.pos):
                self.app.difficulty = b.tag
                return
        for i, r in enumerate(self.cards()):
            if r.collidepoint(event.pos):
                self.app.start_puzzle(PUZZLE_IDS[i], self.app.difficulty)
                return

    def draw(self, surf, t):
        g = self.game
        text(surf, "CHOOSE A PUZZLE", (SCREEN_W // 2, 126), "big", C_INK, center=True)
        for b in self.diff_buttons():
            if b.tag == self.app.difficulty:
                b.color = C_GOLD_DARK
            b.draw(surf, pygame.mouse.get_pos())
        if not g.difficulty_unlocked("medium"):
            text(surf, "Solve 5 puzzles to unlock Medium, 14 for Hard.",
                 (SCREEN_W // 2, 176), "small", C_INK_SOFT, center=True)
        mouse = pygame.mouse.get_pos()
        for i, r in enumerate(self.cards()):
            pid = PUZZLE_IDS[i]
            meta = PUZZLES[pid]
            hover = r.collidepoint(mouse)
            panel(surf, r, C_WHITE if hover else C_PANEL, border=meta["color"], width=3)
            pygame.draw.rect(surf, meta["color"], (r.x, r.y, r.w, 8),
                             border_top_left_radius=12, border_top_right_radius=12)
            text(surf, meta["name"], (r.centerx, r.y + 30), "bodyb", C_INK, center=True)
            # part badge
            part = meta["part"]
            got = g.parts[part]
            text(surf, PART_NAMES[part], (r.centerx, r.y + 54), "tiny",
                 C_GREEN_DARK if got else C_INK_SOFT, center=True)
            pygame.draw.circle(surf, C_GREEN if got else C_PANEL_DARK, (r.centerx, r.y + 86), 16)
            text(surf, "OK" if got else "?", (r.centerx, r.y + 86), "small",
                 C_WHITE if got else C_INK_SOFT, center=True)
            reward = meta["coins"][self.app.difficulty]
            text(surf, "up to %d coins" % reward, (r.centerx, r.y + 118), "small", C_GOLD_DARK, center=True)
            clears = g.puzzle_clears.get(pid, 0)
            text(surf, "cleared %dx" % clears if clears else "not cleared yet",
                 (r.centerx, r.y + 142), "tiny", C_INK_SOFT, center=True)
            best = g.best_scores.get(pid)
            if best:
                text(surf, "best %d" % best, (r.centerx, r.y + 158), "tiny", C_INK_SOFT, center=True)


# ------------------------------------------------------ PUZZLE PLAY SCREEN ---
class PuzzlePlayScreen(Screen):
    def __init__(self, app, pid, difficulty):
        super().__init__(app)
        self.pid = pid
        self.difficulty = difficulty
        self.puzzle = PUZZLE_CLASSES[pid](self.game, difficulty)
        self.start = time.time()
        self.reward = None
        self.hint_shown = False
        self.quit_btn = Button((SCREEN_W - 150, 122, 110, 36), "Quit", C_RED)
        self.hint_btn = Button((40, 122, 110, 36), "Hint", C_BLUE)
        self.ok_btn = Button((SCREEN_W // 2 - 190, SCREEN_H // 2 + 84, 170, 46), "Continue", C_GREEN)
        self.again_btn = Button((SCREEN_W // 2 + 20, SCREEN_H // 2 + 84, 170, 46), "Play Again", C_BLUE)

    def time_left(self):
        return max(0.0, self.puzzle.time_limit - (time.time() - self.start))

    def handle(self, event):
        if self.reward is not None:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.ok_btn.hit(event.pos):
                    self.app.goto("puzzles")
                elif self.again_btn.hit(event.pos):
                    self.app.start_puzzle(self.pid, self.difficulty)
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.quit_btn.hit(event.pos):
                self.app.goto("puzzles")
                return
            if self.hint_btn.hit(event.pos):
                self.hint_shown = True
                return
        if not self.puzzle.done:
            self.puzzle.handle(event, PLAY_AREA)

    def update(self, dt):
        if self.reward is not None:
            return
        if not self.puzzle.done:
            self.puzzle.update(dt)
            if self.time_left() <= 0:
                self.puzzle.on_timeout()
        if self.puzzle.done and self.reward is None:
            if self.puzzle.won:
                self.reward = self.game.complete_puzzle(self.pid, self.difficulty, self.puzzle.score)
                self.app.after_change()
            else:
                self.reward = dict(coins=0, xp=0, part=None, first=False, levels=[])

    def draw(self, surf, t):
        meta = PUZZLES[self.pid]
        text(surf, meta["name"], (SCREEN_W // 2, 126), "big", C_INK, center=True)
        text(surf, self.puzzle.objective, (SCREEN_W // 2, 158), "body", C_INK_SOFT, center=True)
        # timer
        frac = self.time_left() / self.puzzle.time_limit
        bar = pygame.Rect(SCREEN_W // 2 - 180, 182, 360, 10)
        progress_bar(surf, bar, frac, C_GREEN if frac > 0.3 else C_RED)
        text(surf, "%ds" % int(self.time_left()), (bar.right + 34, 187), "bodyb",
             C_INK_SOFT, center=True)
        text(surf, DIFF_LABEL[self.difficulty], (bar.x - 40, 187), "bodyb", C_INK_SOFT, center=True)

        panel(surf, PLAY_AREA, C_PANEL, border=C_PANEL_DARK)
        self.puzzle.draw(surf, PLAY_AREA, t)
        mouse = pygame.mouse.get_pos()
        self.quit_btn.draw(surf, mouse)
        self.hint_btn.draw(surf, mouse)
        if self.hint_shown:
            text(surf, self.puzzle.hint_text, (SCREEN_W // 2, PLAY_AREA.bottom + 16),
                 "small", C_BLUE, center=True)
        if self.reward is not None:
            self.draw_result(surf, t)

    def draw_result(self, surf, t):
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 120))
        surf.blit(shade, (0, 0))
        box = pygame.Rect(SCREEN_W // 2 - 240, SCREEN_H // 2 - 170, 480, 330)
        panel(surf, box, C_PANEL, border=C_GOLD_DARK, width=4)
        won = self.puzzle.won
        text(surf, "PUZZLE SOLVED!" if won else "OUT OF LUCK",
             (box.centerx, box.y + 42), "big", C_GREEN_DARK if won else C_RED, center=True)
        text(surf, "Score: %d / 100" % self.puzzle.score, (box.centerx, box.y + 84),
             "mid", C_INK, center=True)
        y = box.y + 124
        if won:
            text(surf, "+ %d coins" % self.reward["coins"], (box.centerx, y), "mid", C_GOLD_DARK, center=True)
            y += 32
            text(surf, "+ %d XP" % self.reward["xp"], (box.centerx, y), "body", C_PURPLE, center=True)
            y += 30
            if self.reward["part"]:
                text(surf, "NEW ROBOT PART:  %s" % PART_NAMES[self.reward["part"]].upper(),
                     (box.centerx, y), "bodyb", C_BLUE, center=True)
            else:
                text(surf, "Part already collected - coins only.", (box.centerx, y),
                     "small", C_INK_SOFT, center=True)
        else:
            text(surf, "No coins this time. Try again!", (box.centerx, y), "body", C_INK_SOFT, center=True)
        mouse = pygame.mouse.get_pos()
        self.ok_btn.draw(surf, mouse)
        self.again_btn.draw(surf, mouse)


# ----------------------------------------------------------- BUILD SCREEN ----
class BuildScreen(Screen):
    def zone_buttons(self):
        out = []
        w = 156
        total = len(ZONES) * w + (len(ZONES) - 1) * 10
        x0 = SCREEN_W // 2 - total // 2
        for i, z in enumerate(ZONES):
            out.append(Button((x0 + i * (w + 10), 126, w, 38), ZONE_LABEL[z],
                              C_GOLD_DARK if z == self.app.zone else C_BLUE, tag=z))
        return out

    def zone_items(self):
        return [bid for bid, d in BUILDINGS.items() if d["zone"] == self.app.zone]

    def cards(self, n):
        cols = 4
        rows = max(1, (n + cols - 1) // cols)
        return grid_rects(pygame.Rect(60, 184, SCREEN_W - 120, 420), cols, rows, 226, 150, 18, 0)

    def handle(self, event):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for b in self.zone_buttons():
            if b.hit(event.pos):
                self.app.zone = b.tag
                return
        items = self.zone_items()
        for i, r in enumerate(self.cards(len(items))):
            if i >= len(items):
                break
            if r.collidepoint(event.pos):
                bid = items[i]
                if not self.game.is_unlocked(bid):
                    self.app.notify(self.game.unlock_text(bid), C_RED)
                elif not self.game.can_afford(self.game.building_cost(bid)):
                    self.app.notify("You need %d coins for that." % self.game.building_cost(bid), C_RED)
                else:
                    self.app.selected_build = bid
                    self.app.goto("map")
                    self.app.notify("Click a green tile to place your %s." % BUILDINGS[bid]["name"])
                return

    def draw(self, surf, t):
        g = self.game
        text(surf, "BUILDING SHOP", (SCREEN_W // 2, 104), "big", C_INK, center=True)
        mouse = pygame.mouse.get_pos()
        for b in self.zone_buttons():
            b.draw(surf, mouse)
        items = self.zone_items()
        for i, r in enumerate(self.cards(len(items))):
            if i >= len(items):
                break
            bid = items[i]
            d = BUILDINGS[bid]
            unlocked = g.is_unlocked(bid)
            cost = g.building_cost(bid)
            afford = g.can_afford(cost)
            border = C_GREEN if (unlocked and afford) else (C_LOCK if not unlocked else C_RED)
            panel(surf, r, C_PANEL if unlocked else C_PANEL_DARK, border=border, width=3)
            preview = pygame.Rect(r.x + 10, r.y + 12, 56, 56)
            pygame.draw.rect(surf, C_GRASS, preview, border_radius=6)
            draw_building(surf, bid, preview, t)
            text(surf, d["name"], (r.x + 78, r.y + 16), "bodyb", C_INK if unlocked else C_INK_SOFT)
            text(surf, "%d coins" % cost, (r.x + 78, r.y + 40), "body",
                 C_GOLD_DARK if afford else C_RED)
            if unlocked:
                bits = []
                if d["pop"]:
                    bits.append("+%d pop" % d["pop"])
                if d["happy"]:
                    bits.append("%+d happy" % d["happy"])
                if d["income"]:
                    bits.append("+%d/min" % d["income"])
                text(surf, "   ".join(bits) or "decoration", (r.x + 12, r.y + 86), "small", C_INK_SOFT)
                text(surf, "Click to place", (r.x + 12, r.y + 112), "small", C_GREEN_DARK)
            else:
                text(surf, "LOCKED", (r.x + 12, r.y + 86), "bodyb", C_LOCK)
                text(surf, g.unlock_text(bid), (r.x + 12, r.y + 112), "small", C_INK_SOFT)


# ------------------------------------------------------------ FARM SCREEN ----
class FarmScreen(Screen):
    harvest_btn = Button((SCREEN_W - 210, 96, 170, 38), "Harvest All", C_ORANGE)

    def crop_buttons(self):
        out = []
        ids = list(CROPS.keys())
        w = 152
        total = len(ids) * w + (len(ids) - 1) * 10
        x0 = SCREEN_W // 2 - total // 2
        for i, cid in enumerate(ids):
            c = CROPS[cid]
            out.append(Button((x0 + i * (w + 10), 150, w, 42),
                              "%s  %dc" % (c["name"], c["cost"]),
                              C_GOLD_DARK if cid == self.app.crop else C_GREEN, tag=cid))
        return out

    def plots(self, n):
        cols = 6
        rows = max(1, (n + cols - 1) // cols)
        return grid_rects(pygame.Rect(60, 215, SCREEN_W - 120, 380), cols, rows, 150, 128, 16, 0)

    def handle(self, event):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for b in self.crop_buttons():
            if b.hit(event.pos):
                self.app.crop = b.tag
                return
        if self.harvest_btn.hit(event.pos):
            n = self.game.harvest_all()
            self.app.notify("Harvested %d field(s)." % n if n else "Nothing is ready yet.",
                            C_GREEN_DARK if n else C_RED)
            self.app.after_change()
            return
        fields = self.game.fields
        for i, r in enumerate(self.plots(len(fields))):
            if i >= len(fields):
                break
            if r.collidepoint(event.pos):
                f = fields[i]
                st = self.game.field_state(f)
                if st == "empty":
                    ok, msg = self.game.plant(f, self.app.crop)
                elif st == "ready":
                    ok, msg = self.game.harvest(f)
                else:
                    ok, msg = False, "Still growing..."
                self.app.notify(msg, C_INK if ok else C_RED)
                self.app.after_change()
                return

    def draw(self, surf, t):
        g = self.game
        fields = g.fields
        text(surf, "FARM", (SCREEN_W // 2, 100), "big", C_INK, center=True)
        text(surf, "Pick a seed, then click an empty plot. Click a golden plot to harvest.",
             (SCREEN_W // 2, 128), "small", C_INK_SOFT, center=True)
        mouse = pygame.mouse.get_pos()
        for b in self.crop_buttons():
            b.draw(surf, mouse)
        self.harvest_btn = Button((SCREEN_W - 210, 96, 170, 38), "Harvest All", C_ORANGE)
        self.harvest_btn.draw(surf, mouse)

        if not fields:
            text(surf, "You have no crop fields yet.", (SCREEN_W // 2, 320), "mid", C_INK_SOFT, center=True)
            text(surf, "Buy a Crop Field in the BUILD screen (90 coins) and place it on your land.",
                 (SCREEN_W // 2, 356), "body", C_INK_SOFT, center=True)
            return

        sel = CROPS[self.app.crop]
        for i, r in enumerate(self.plots(len(fields))):
            if i >= len(fields):
                break
            f = fields[i]
            st = g.field_state(f)
            border = {"empty": C_INK_SOFT, "growing": C_GREEN, "ready": C_GOLD_DARK}[st]
            panel(surf, r, C_PANEL, border=border, width=3)
            inner = pygame.Rect(r.x + 8, r.y + 24, r.w - 16, r.h - 58)
            draw_field(surf, g, f, inner, t)
            text(surf, "Plot %d" % (i + 1), (r.x + 10, r.y + 6), "small", C_INK_SOFT)
            if st == "empty":
                text(surf, "Plant %s (%dc)" % (sel["name"], sel["cost"]),
                     (r.centerx, r.bottom - 18), "small", C_GREEN_DARK, center=True)
            elif st == "growing":
                left = int(g.grow_time(f["crop"]) - (time.time() - f["planted"]))
                text(surf, "%s  -  %ds left" % (CROPS[f["crop"]]["name"], max(0, left)),
                     (r.centerx, r.bottom - 18), "small", C_INK_SOFT, center=True)
            else:
                text(surf, "READY  +%d coins" % CROPS[f["crop"]]["sell"],
                     (r.centerx, r.bottom - 18), "bodyb", C_GOLD_DARK, center=True)


# ----------------------------------------------------------- ROBOT SCREEN ----
class RobotScreen(Screen):
    up_btn = None

    def part_rects(self):
        return grid_rects(pygame.Rect(60, 180, 520, 400), 5, 2, 92, 92, 14, 0)

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and self.up_btn and self.up_btn.hit(event.pos):
            ok, msg = self.game.upgrade_robot()
            self.app.notify(msg, C_INK if ok else C_RED)
            self.app.after_change()

    def draw(self, surf, t):
        g = self.game
        text(surf, "ROBOT WORKSHOP", (SCREEN_W // 2, 100), "big", C_INK, center=True)
        text(surf, "Robot Collection:  %d / %d Parts" % (g.part_count, len(PART_ORDER)),
             (300, 140), "mid", C_INK, center=True)
        progress_bar(surf, pygame.Rect(120, 162, 360, 12), g.part_count / len(PART_ORDER), C_BLUE)

        for i, r in enumerate(self.part_rects()):
            pid = PART_ORDER[i]
            got = g.parts[pid]
            panel(surf, r, (222, 238, 250) if got else C_PANEL_DARK,
                  border=C_BLUE if got else C_LOCK, width=3)
            text(surf, PART_NAMES[pid], (r.centerx, r.centery - 8), "small",
                 C_INK if got else C_INK_SOFT, center=True)
            text(surf, "COLLECTED" if got else "missing", (r.centerx, r.centery + 16), "tiny",
                 C_GREEN_DARK if got else C_LOCK, center=True)
            if not got:
                src = next(p for p, m in PUZZLES.items() if m["part"] == pid)
                text(surf, PUZZLES[src]["name"], (r.centerx, r.centery + 32), "tiny",
                     C_INK_SOFT, center=True)

        # big robot
        stage = pygame.Rect(600, 150, 200, 300)
        panel(surf, stage, C_PANEL, border=C_PANEL_DARK)
        draw_robot(surf, stage.centerx, stage.centery + 10, 1.5, g.parts, t)
        if g.robot_assembled:
            text(surf, "ASSEMBLED!", (stage.centerx, stage.bottom - 22), "bodyb",
                 C_GREEN_DARK, center=True)
        else:
            text(surf, "Solve more puzzles", (stage.centerx, stage.bottom - 22), "small",
                 C_INK_SOFT, center=True)

        # upgrades
        up = pygame.Rect(830, 150, 230, 420)
        panel(surf, up, C_PANEL, border=C_PANEL_DARK)
        text(surf, "UPGRADES", (up.x + 16, up.y + 14), "mid", C_INK)
        y = up.y + 48
        for lvl in sorted(ROBOT_UPGRADES):
            have = g.robot_level >= lvl
            col = C_GREEN_DARK if have else C_INK_SOFT
            text(surf, "Level %d%s" % (lvl, "  (active)" if have else ""), (up.x + 16, y), "bodyb", col)
            y += 20
            words = ROBOT_UPGRADES[lvl]["perk"].split()
            line = ""
            for w in words:
                if len(line) + len(w) > 30:
                    text(surf, line, (up.x + 16, y), "tiny", C_INK_SOFT)
                    y += 15
                    line = ""
                line += w + " "
            text(surf, line, (up.x + 16, y), "tiny", C_INK_SOFT)
            y += 24
        nxt = g.robot_level + 1
        self.up_btn = None
        if nxt in ROBOT_UPGRADES:
            cost = ROBOT_UPGRADES[nxt]["cost"]
            enabled = g.robot_assembled and g.can_afford(cost)
            self.up_btn = Button((up.x + 16, up.bottom - 56, up.w - 32, 40),
                                 "Upgrade  (%d)" % cost, C_PURPLE, enabled=enabled)
            self.up_btn.draw(surf, pygame.mouse.get_pos())
        else:
            text(surf, "Fully upgraded!", (up.centerx, up.bottom - 36), "bodyb",
                 C_GREEN_DARK, center=True)


# -------------------------------------------------------- MISSIONS SCREEN ----
class MissionsScreen(Screen):
    def mission_rects(self):
        return [pygame.Rect(60, 160 + i * 58, 620, 48) for i in range(len(MISSIONS))]

    def handle(self, event):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for i, r in enumerate(self.mission_rects()):
            m = MISSIONS[i]
            btn = pygame.Rect(r.right - 118, r.y + 7, 106, 34)
            if btn.collidepoint(event.pos):
                ok, msg = self.game.claim_mission(m["id"])
                if ok:
                    self.app.notify(msg, C_GOLD_DARK)
                    self.app.after_change()
                return

    def draw(self, surf, t):
        g = self.game
        text(surf, "MISSIONS", (370, 122), "big", C_INK, center=True)
        mouse = pygame.mouse.get_pos()
        for i, r in enumerate(self.mission_rects()):
            m = MISSIONS[i]
            prog = g.mission_progress(m)
            done = m["id"] in g.missions_done
            claimed = m["id"] in g.missions_claimed
            panel(surf, r, C_PANEL, border=C_GREEN if done else C_PANEL_DARK,
                  width=3 if done else 2)
            text(surf, m["text"], (r.x + 14, r.y + 6), "bodyb", C_INK)
            text(surf, "%d / %d" % (prog, m["target"]), (r.x + 14, r.y + 28), "small", C_INK_SOFT)
            progress_bar(surf, pygame.Rect(r.x + 90, r.y + 32, 240, 8), prog / m["target"])
            text(surf, "+%d" % m["reward"], (r.right - 132, r.y + 24), "bodyb",
                 C_GOLD_DARK, right=True)
            if claimed:
                text(surf, "CLAIMED", (r.right - 62, r.y + 24), "small", C_GREEN_DARK, center=True)
            else:
                Button((r.right - 118, r.y + 7, 106, 34), "Claim", C_GOLD_DARK,
                       enabled=done).draw(surf, mouse)

        # achievements
        ach = pygame.Rect(710, 150, 350, 440)
        panel(surf, ach, C_PANEL, border=C_PANEL_DARK)
        text(surf, "ACHIEVEMENTS", (ach.x + 16, ach.y + 14), "mid", C_INK)
        for i, a in enumerate(ACHIEVEMENTS):
            row = pygame.Rect(ach.x + 14, ach.y + 50 + i * 46, ach.w - 28, 40)
            got = a["id"] in g.achievements
            panel(surf, row, (238, 244, 232) if got else C_PANEL_DARK,
                  border=C_GOLD_DARK if got else C_LOCK, width=2)
            pygame.draw.circle(surf, C_GOLD if got else C_LOCK, (row.x + 22, row.centery), 13)
            text(surf, a["name"], (row.x + 46, row.y + 4), "bodyb", C_INK if got else C_INK_SOFT)
            text(surf, "unlocked" if got else "%d / %d" % (g.stat_value(a["stat"]), a["target"]),
                 (row.x + 46, row.y + 22), "tiny", C_INK_SOFT)


# ==============================================================================
# SECTION 8 - APPLICATION
# Owns the window, the HUD, navigation, autosave and the main loop.
# ==============================================================================

NAV_ITEMS = [("map", "TOWNSHIP"), ("puzzles", "PUZZLES"), ("build", "BUILD"),
             ("farm", "FARM"), ("robot", "ROBOT"), ("missions", "MISSIONS")]


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Robot Puzzle Adventure & Township Builder")
        self.surf = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        init_fonts()

        self.game = Game()
        self.loaded = load_game(self.game)
        self.toasts = Toasts()

        self.selected_build = None
        self.cancel_btn = None
        self.difficulty = "easy"
        self.zone = "residential"
        self.crop = "wheat"

        self.screens = {}
        self.screen_name = "map"
        self.screen = MapScreen(self)
        self.snapshot()

        self.last_tick = time.time()
        self.last_save = time.time()
        self.running = True

        if self.loaded:
            self.notify("Welcome back! Save file loaded.", C_GREEN_DARK)
        else:
            self.notify("New township started. Solve a puzzle to begin!", C_BLUE)

    # ---------------------------------------------------------- helpers ----
    def notify(self, msg, color=C_INK):
        if msg:
            self.toasts.push(msg, color)

    def snapshot(self):
        self._snap = (self.game.population, self.game.level, self.game.robot_assembled)

    def after_change(self):
        """Run after anything that could change progression."""
        pop, lvl, rob = self._snap
        for bid in self.game.newly_unlocked(pop, lvl, rob):
            self.notify("UNLOCKED: %s" % BUILDINGS[bid]["name"], C_PURPLE)
        if self.game.robot_assembled and not rob:
            self.notify("ROBOT ASSEMBLED! It now helps around the township.", C_GREEN_DARK)
        if self.game.level > lvl:
            self.notify("Level up!  You are now level %d." % self.game.level, C_PURPLE)
        for kind, name in self.game.refresh_goals():
            self.notify(("Mission complete: %s" if kind == "mission" else "Achievement: %s") % name,
                        C_GOLD_DARK)
        self.snapshot()
        save_game(self.game)

    def goto(self, name):
        self.screen_name = name
        if name == "map":
            self.screen = MapScreen(self)
        elif name == "puzzles":
            self.screen = PuzzleHubScreen(self)
        elif name == "build":
            self.screen = BuildScreen(self)
        elif name == "farm":
            self.screen = FarmScreen(self)
        elif name == "robot":
            self.screen = RobotScreen(self)
        elif name == "missions":
            self.screen = MissionsScreen(self)

    def start_puzzle(self, pid, difficulty):
        self.screen_name = "play"
        self.screen = PuzzlePlayScreen(self, pid, difficulty)

    # ---------------------------------------------------------- chrome -----
    def nav_buttons(self):
        w = 168
        total = len(NAV_ITEMS) * w + (len(NAV_ITEMS) - 1) * 8
        x0 = SCREEN_W // 2 - total // 2
        y = SCREEN_H - NAV_H + 8
        out = []
        for i, (key, label) in enumerate(NAV_ITEMS):
            active = (self.screen_name == key) or (self.screen_name == "play" and key == "puzzles")
            out.append(Button((x0 + i * (w + 8), y, w, NAV_H - 16), label,
                              C_GOLD_DARK if active else C_GREEN, tag=key))
        return out

    def draw_hud(self):
        g = self.game
        panel(self.surf, pygame.Rect(0, 0, SCREEN_W, HUD_H), C_PANEL, radius=0)
        pygame.draw.line(self.surf, C_PANEL_DARK, (0, HUD_H), (SCREEN_W, HUD_H), 3)
        chips = [
            ("COINS", "%d" % g.coins, C_GOLD_DARK),
            ("POPULATION", "%d" % g.population, C_BLUE),
            ("HAPPINESS", "%d%%" % g.happiness,
             C_GREEN_DARK if g.happiness >= 60 else C_RED),
            ("ROBOT", "%d/%d parts" % (g.part_count, len(PART_ORDER)), C_PURPLE),
            ("LEVEL", "%d" % g.level, C_ORANGE),
            ("HOUSES", "%d" % g.houses, C_INK_SOFT),
        ]
        x = 24
        for label, value, col in chips:
            text(self.surf, label, (x, 10), "tiny", C_INK_SOFT)
            text(self.surf, value, (x, 26), "mid", col)
            x += 172
        text(self.surf, "S = save    N = new game    ESC = township",
             (SCREEN_W - 24, 34), "tiny", C_INK_SOFT, right=True)

        # objective banner
        band = pygame.Rect(24, HUD_H + 8, SCREEN_W - 48, 34)
        panel(self.surf, band, (250, 242, 214), border=C_GOLD)
        text(self.surf, "NEXT:  " + self.game.next_objective(),
             (band.centerx, band.centery), "body", C_INK, center=True)

    # ---------------------------------------------------------- loop -------
    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            t = time.time() % 10000
            self.handle_events()

            self.screen.update(dt)
            if time.time() - self.last_tick >= 1.0:
                self.last_tick = time.time()
                for msg in self.game.tick():
                    self.notify(msg, C_GREEN_DARK)
            if time.time() - self.last_save >= 20:
                self.last_save = time.time()
                save_game(self.game)

            self.surf.fill(C_SKY)
            self.screen.draw(self.surf, t)
            self.draw_hud()
            mouse = pygame.mouse.get_pos()
            panel(self.surf, pygame.Rect(0, SCREEN_H - NAV_H, SCREEN_W, NAV_H), C_PANEL, radius=0)
            for b in self.nav_buttons():
                b.draw(self.surf, mouse)
            self.toasts.draw(self.surf)
            pygame.display.flip()

        save_game(self.game)
        pygame.quit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.goto("map")
                    continue
                if self.screen_name == "play" and event.key not in (pygame.K_ESCAPE,):
                    self.screen.handle(event)
                    continue
                if event.key == pygame.K_s:
                    self.notify("Game saved." if save_game(self.game) else "Save failed.", C_BLUE)
                    continue
                if event.key == pygame.K_n and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    self.game.new_game()
                    save_game(self.game)
                    self.snapshot()
                    self.goto("map")
                    self.notify("New township started.", C_BLUE)
                    continue
                if event.key == pygame.K_n:
                    self.notify("Press SHIFT+N to confirm starting a new game.", C_RED)
                    continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for b in self.nav_buttons():
                    if b.hit(event.pos):
                        self.goto(b.tag)
                        break
                else:
                    self.screen.handle(event)
                    continue
                continue
            self.screen.handle(event)


def main():
    App().run()


if __name__ == "__main__":
    main()
