"""
DIMENSION RUNNER
================
An endless runner where the same stretch of "track" is simulated in four
parallel dimensions at once. Only the dimension you are currently in is
visible and dangerous - press D to jump between them and dodge whatever
is coming.

Controls:
    LEFT / RIGHT  - move
    SPACE         - jump
    D             - switch dimension
    P / ESC       - pause
    ENTER         - confirm / restart / start

Run with:  python dimension_runner.py
Requires:  pygame   (pip install pygame)
"""

import pygame
import random
import math
import json
import os

# --------------------------------------------------------------------------
# CONSTANTS
# --------------------------------------------------------------------------
WIDTH, HEIGHT = 960, 600
FPS = 60
GROUND_Y = 460

GRAVITY = 1900.0
JUMP_VELOCITY = -720.0
SPACE_GRAVITY_MULT = 0.55          # low gravity feel in the Space dimension

PLAYER_W, PLAYER_H = 38, 52
PLAYER_MOVE_SPEED = 420.0
PLAYER_X_MIN, PLAYER_X_MAX = 70, 760

BASE_SCROLL_SPEED = 320.0
MAX_SCROLL_SPEED = 780.0
SPEED_RAMP_PER_SEC = 2.4            # how fast the world speeds up

DIMENSION_SWITCH_COOLDOWN = 0.35
HIT_INVULN_TIME = 1.3

HIGHSCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dimension_runner_highscore.json")

# Dimension indices
EARTH, FIRE, ICE, SPACE = 0, 1, 2, 3

DIMENSIONS = [
    {
        "name": "Earth", "emoji": "EARTH", "symbol": "E",
        "sky_top": (110, 190, 235), "sky_bottom": (196, 228, 176),
        "ground": (86, 150, 60), "ground2": (66, 120, 44),
        "accent": (139, 90, 43), "particle": (255, 255, 255),
        "gravity_mult": 1.0,
    },
    {
        "name": "Fire", "emoji": "FIRE", "symbol": "F",
        "sky_top": (70, 10, 10), "sky_bottom": (255, 110, 20),
        "ground": (48, 18, 10), "ground2": (30, 10, 6),
        "accent": (255, 150, 40), "particle": (255, 200, 60),
        "gravity_mult": 1.05,
    },
    {
        "name": "Ice", "emoji": "ICE", "symbol": "I",
        "sky_top": (190, 225, 255), "sky_bottom": (240, 248, 255),
        "ground": (207, 232, 250), "ground2": (170, 205, 230),
        "accent": (120, 180, 220), "particle": (255, 255, 255),
        "gravity_mult": 0.95,
    },
    {
        "name": "Space", "emoji": "SPACE", "symbol": "S",
        "sky_top": (6, 6, 28), "sky_bottom": (32, 12, 56),
        "ground": (46, 44, 66), "ground2": (30, 28, 46),
        "accent": (170, 120, 255), "particle": (200, 200, 255),
        "gravity_mult": SPACE_GRAVITY_MULT,
    },
]

# Obstacle templates per dimension: (type, kind, w, h, jumpable)
# kind: "scroll" (moves with the world, fixed y=ground) or "fall" (drops from sky at fixed x)
OBSTACLE_TEMPLATES = {
    EARTH: [
        {"type": "rock",   "kind": "scroll", "w": 46, "h": 46,  "jumpable": True},
        {"type": "tree",   "kind": "scroll", "w": 54, "h": 190, "jumpable": False},
        {"type": "branch", "kind": "fall",   "w": 30, "h": 30,  "jumpable": False},
    ],
    FIRE: [
        {"type": "ember",  "kind": "scroll", "w": 44, "h": 44,  "jumpable": True},
        {"type": "pillar", "kind": "scroll", "w": 40, "h": 200, "jumpable": False},
        {"type": "fireball","kind": "fall",  "w": 30, "h": 30,  "jumpable": False},
    ],
    ICE: [
        {"type": "iceblock","kind": "scroll","w": 50, "h": 48,  "jumpable": True},
        {"type": "icespike","kind": "scroll","w": 38, "h": 195, "jumpable": False},
        {"type": "icicle",  "kind": "fall",  "w": 24, "h": 34,  "jumpable": False},
    ],
    SPACE: [
        {"type": "debris",  "kind": "scroll","w": 46, "h": 46,  "jumpable": True},
        {"type": "wall",    "kind": "scroll","w": 44, "h": 210, "jumpable": False},
        {"type": "meteor",  "kind": "fall",  "w": 32, "h": 32,  "jumpable": False},
    ],
}

POWERUP_TYPES = ["shield", "magnet", "boost"]

# --------------------------------------------------------------------------
# UTILITIES
# --------------------------------------------------------------------------

def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def draw_vertical_gradient(surface, rect, top_color, bottom_color):
    x, y, w, h = rect
    if h <= 0:
        return
    for i in range(h):
        t = i / h
        color = lerp_color(top_color, bottom_color, t)
        pygame.draw.line(surface, color, (x, y + i), (x + w, y + i))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def load_highscore():
    try:
        with open(HIGHSCORE_FILE, "r") as f:
            return json.load(f).get("highscore", 0)
    except Exception:
        return 0


def save_highscore(value):
    try:
        with open(HIGHSCORE_FILE, "w") as f:
            json.dump({"highscore": value}, f)
    except Exception:
        pass


# --------------------------------------------------------------------------
# PARTICLES
# --------------------------------------------------------------------------
class Particle:
    def __init__(self, x, y, color, vx=0, vy=0, life=0.6, radius=4, gravity=0.0):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = life
        self.max_life = life
        self.color = color
        self.radius = radius
        self.gravity = gravity

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt
        self.life -= dt
        return self.life > 0

    def draw(self, surf):
        t = clamp(self.life / self.max_life, 0, 1)
        r = max(1, int(self.radius * t))
        alpha = int(255 * t)
        s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, alpha), (r + 1, r + 1), r)
        surf.blit(s, (self.x - r - 1, self.y - r - 1))


class ParticleSystem:
    def __init__(self):
        self.particles = []

    def burst(self, x, y, color, count=14, speed=180, life=0.6, gravity=300, radius=4):
        for _ in range(count):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(speed * 0.3, speed)
            vx = math.cos(ang) * spd
            vy = math.sin(ang) * spd - 60
            self.particles.append(Particle(x, y, color, vx, vy, life, radius, gravity))

    def emit(self, x, y, color, vx=0, vy=0, life=0.5, radius=3, gravity=0):
        self.particles.append(Particle(x, y, color, vx, vy, life, radius, gravity))

    def update(self, dt):
        self.particles = [p for p in self.particles if p.update(dt)]

    def draw(self, surf):
        for p in self.particles:
            p.draw(surf)


# --------------------------------------------------------------------------
# PLAYER
# --------------------------------------------------------------------------
class Player:
    def __init__(self):
        self.x = 220.0
        self.y = GROUND_Y - PLAYER_H
        self.vx = 0.0
        self.vy = 0.0
        self.w, self.h = PLAYER_W, PLAYER_H
        self.on_ground = True
        self.lives = 3
        self.shield = False
        self.magnet_timer = 0.0
        self.boost_timer = 0.0
        self.invuln_timer = 0.0
        self.run_cycle = 0.0
        self.squash = 1.0

    @property
    def rect(self):
        # slightly shrink hitbox for fairness
        pad_x, pad_y = 6, 4
        return pygame.Rect(self.x + pad_x, self.y + pad_y, self.w - pad_x * 2, self.h - pad_y * 2)

    def jump(self):
        if self.on_ground:
            self.vy = JUMP_VELOCITY
            self.on_ground = False

    def hit(self, particles):
        if self.invuln_timer > 0:
            return False
        if self.shield:
            self.shield = False
            particles.burst(self.x + self.w / 2, self.y + self.h / 2, (120, 200, 255), 20, 220)
            self.invuln_timer = 0.6
            return False
        self.lives -= 1
        self.invuln_timer = HIT_INVULN_TIME
        particles.burst(self.x + self.w / 2, self.y + self.h / 2, (255, 80, 80), 24, 260)
        return True

    def update(self, dt, dimension_idx, move_dir):
        gravity_mult = DIMENSIONS[dimension_idx]["gravity_mult"]
        speed_mult = 1.35 if self.boost_timer > 0 else 1.0

        self.vx = move_dir * PLAYER_MOVE_SPEED * speed_mult
        self.x += self.vx * dt
        self.x = clamp(self.x, PLAYER_X_MIN, PLAYER_X_MAX)

        self.vy += GRAVITY * gravity_mult * dt
        self.y += self.vy * dt

        ground_top = GROUND_Y - self.h
        if self.y >= ground_top:
            self.y = ground_top
            if not self.on_ground and self.vy > 400:
                self.squash = 0.7
            self.vy = 0
            self.on_ground = True
        else:
            self.on_ground = False

        self.squash += (1.0 - self.squash) * min(1, dt * 10)

        if self.on_ground:
            self.run_cycle += dt * (10 if abs(self.vx) > 10 else 4)
        if self.magnet_timer > 0:
            self.magnet_timer -= dt
        if self.boost_timer > 0:
            self.boost_timer -= dt
        if self.invuln_timer > 0:
            self.invuln_timer -= dt

    def draw(self, surf, dimension_idx):
        accent = DIMENSIONS[dimension_idx]["accent"]
        flicker = (self.invuln_timer > 0) and (int(self.invuln_timer * 20) % 2 == 0)
        if flicker:
            return

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        wing_offset = math.sin(self.run_cycle * 1.5) * 5

        # shadow
        pygame.draw.ellipse(surf, (40, 40, 40), (cx - 18, self.y + self.h - 2, 36, 8))
        # body
        pygame.draw.ellipse(surf, (245, 245, 245), (cx - 18, cy - 15, 36, 30))
        # head
        pygame.draw.circle(surf, (250, 250, 250), (int(cx + 13), int(cy - 14)), 14)
        # wing
        pygame.draw.ellipse(surf, accent, (cx - 16, cy - 8 + wing_offset, 25, 16))
        # beak
        pygame.draw.polygon(surf, (255, 170, 40),
                             [(cx + 25, cy - 14), (cx + 38, cy - 8), (cx + 25, cy - 3)])
        # eye
        pygame.draw.circle(surf, (30, 30, 30), (int(cx + 17), int(cy - 18)), 4)
        pygame.draw.circle(surf, (255, 255, 255), (int(cx + 18), int(cy - 19)), 1)
        # tail
        pygame.draw.polygon(surf, accent,
                             [(cx - 15, cy), (cx - 32, cy - 12), (cx - 27, cy + 5),
                              (cx - 35, cy + 15), (cx - 10, cy + 10)])
        # legs
        pygame.draw.line(surf, (100, 70, 30), (cx - 6, cy + 12), (cx - 9, cy + 22), 3)
        pygame.draw.line(surf, (100, 70, 30), (cx + 7, cy + 12), (cx + 10, cy + 22), 3)

        if self.shield:
            pygame.draw.circle(surf, (120, 200, 255), (int(cx), int(cy)), 35, 2)
        if self.boost_timer > 0:
            for i in range(3):
                pygame.draw.line(surf, (255, 210, 90),
                                  (cx - 25 - i * 7, cy + 5), (cx - 38 - i * 7, cy + 5), 3)


# --------------------------------------------------------------------------
# WORLD OBJECTS: Obstacle, Coin, PowerUp
# --------------------------------------------------------------------------
class Obstacle:
    def __init__(self, dimension_idx, template, scroll_speed):
        self.dim = dimension_idx
        self.type = template["type"]
        self.kind = template["kind"]
        self.w = template["w"]
        self.h = template["h"]
        self.jumpable = template["jumpable"]
        self.alive = True

        if self.kind == "scroll":
            self.x = WIDTH + random.randint(0, 120)
            self.y = GROUND_Y - self.h
            self.vx = -scroll_speed
            self.vy = 0
        else:  # "fall"
            self.x = random.uniform(PLAYER_X_MIN, PLAYER_X_MAX + 120)
            self.y = -self.h - random.randint(0, 160)
            self.vx = -scroll_speed * 0.35   # fallers drift slowly with the world too
            self.vy = random.uniform(340, 460)

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def update(self, dt, scroll_speed):
        if self.kind == "scroll":
            self.vx = -scroll_speed
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.kind == "fall" and self.y + self.h >= GROUND_Y:
            self.y = GROUND_Y - self.h
            self.vy = 0
            self.vx = -scroll_speed
            self.kind = "scroll"  # settles and scrolls off after landing
            self._settle_timer = getattr(self, "_settle_timer", 0.35)
        if hasattr(self, "_settle_timer"):
            self._settle_timer -= dt
            if self._settle_timer <= 0:
                self.alive = False
        if self.x + self.w < -50:
            self.alive = False

    def draw(self, surf, colors):
        accent = colors["accent"]
        x, y, w, h = self.x, self.y, self.w, self.h
        if self.type in ("rock", "ember", "iceblock", "debris"):
            pygame.draw.rect(surf, (40, 40, 40), (x + 3, y + 3, w, h), border_radius=6)
            pygame.draw.rect(surf, accent, (x, y, w, h), border_radius=6)
            pygame.draw.rect(surf, lerp_color(accent, (255, 255, 255), 0.3), (x, y, w, h * 0.4), border_radius=6)
        elif self.type in ("tree", "pillar", "icespike", "wall"):
            pygame.draw.rect(surf, (30, 30, 30), (x + 3, y + 3, w, h))
            pygame.draw.polygon(surf, accent, [(x, y + h), (x + w, y + h), (x + w * 0.5, y)])
            pygame.draw.polygon(surf, lerp_color(accent, (255, 255, 255), 0.25),
                                 [(x + w * 0.3, y + h * 0.6), (x + w * 0.7, y + h * 0.6), (x + w * 0.5, y + h * 0.15)])
        else:  # falling: branch, fireball, icicle, meteor
            color = accent if self.type != "fireball" else (255, 140, 30)
            pygame.draw.circle(surf, (0, 0, 0, 60), (int(x + w / 2) + 2, int(y + h / 2) + 2), int(w / 2))
            pygame.draw.circle(surf, color, (int(x + w / 2), int(y + h / 2)), int(w / 2))
            if self.type == "fireball":
                pygame.draw.circle(surf, (255, 230, 150), (int(x + w / 2), int(y + h / 2)), int(w / 4))


class Coin:
    def __init__(self, dimension_idx, scroll_speed):
        self.dim = dimension_idx
        self.x = WIDTH + random.randint(0, 200)
        self.y = random.uniform(GROUND_Y - 220, GROUND_Y - 40)
        self.vx = -scroll_speed
        self.r = 10
        self.alive = True
        self.bob = random.uniform(0, math.tau)

    @property
    def rect(self):
        return pygame.Rect(self.x - self.r, self.y - self.r, self.r * 2, self.r * 2)

    def update(self, dt, scroll_speed, magnet_target=None):
        self.vx = -scroll_speed
        self.bob += dt * 4
        if magnet_target is not None:
            tx, ty = magnet_target
            dx, dy = tx - self.x, ty - self.y
            dist = max(1, math.hypot(dx, dy))
            if dist < 260:
                pull = 900
                self.x += dx / dist * pull * dt
                self.y += dy / dist * pull * dt
        else:
            self.x += self.vx * dt
        self.y += math.sin(self.bob) * 0.6
        if self.x < -30:
            self.alive = False

    def draw(self, surf):
        y = self.y + math.sin(self.bob) * 4
        pygame.draw.circle(surf, (180, 140, 0), (int(self.x), int(y)), self.r)
        pygame.draw.circle(surf, (255, 215, 0), (int(self.x), int(y)), self.r - 2)
        pygame.draw.circle(surf, (255, 245, 180), (int(self.x - 3), int(y - 3)), 2)


class PowerUp:
    def __init__(self, dimension_idx, scroll_speed):
        self.dim = dimension_idx
        self.type = random.choice(POWERUP_TYPES)
        self.x = WIDTH + random.randint(0, 200)
        self.y = random.uniform(GROUND_Y - 180, GROUND_Y - 60)
        self.vx = -scroll_speed
        self.r = 14
        self.alive = True
        self.bob = random.uniform(0, math.tau)

    @property
    def rect(self):
        return pygame.Rect(self.x - self.r, self.y - self.r, self.r * 2, self.r * 2)

    def update(self, dt, scroll_speed):
        self.vx = -scroll_speed
        self.x += self.vx * dt
        self.bob += dt * 3
        if self.x < -30:
            self.alive = False

    def draw(self, surf):
        y = self.y + math.sin(self.bob) * 5
        colors = {"shield": (100, 190, 255), "magnet": (255, 100, 200), "boost": (255, 200, 60)}
        color = colors[self.type]
        pygame.draw.circle(surf, (255, 255, 255), (int(self.x), int(y)), self.r + 3, 2)
        pygame.draw.circle(surf, color, (int(self.x), int(y)), self.r)
        letter = {"shield": "S", "magnet": "M", "boost": "B"}[self.type]
        font = pygame.font.SysFont("arial", 16, bold=True)
        text = font.render(letter, True, (30, 30, 30))
        surf.blit(text, (self.x - text.get_width() / 2, y - text.get_height() / 2))


# --------------------------------------------------------------------------
# GAME
# --------------------------------------------------------------------------
class Game:
    MENU, PLAYING, PAUSED, GAME_OVER = range(4)

    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Dimension Runner")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.SysFont("arial", 18)
        self.font_med = pygame.font.SysFont("arial", 26, bold=True)
        self.font_big = pygame.font.SysFont("arial", 54, bold=True)
        self.font_title = pygame.font.SysFont("arial", 64, bold=True)

        self.highscore = load_highscore()
        self.state = Game.MENU
        self.reset()

    # ---------------- lifecycle ----------------
    def reset(self):
        self.player = Player()
        self.particles = ParticleSystem()
        self.dimension = EARTH
        self.switch_cooldown = 0.0
        self.transition_timer = 0.0

        self.obstacles = {d: [] for d in range(4)}
        self.coins = {d: [] for d in range(4)}
        self.powerups = {d: [] for d in range(4)}
        self.spawn_timers = {d: random.uniform(0.4, 1.0) for d in range(4)}
        self.coin_timers = {d: random.uniform(0.6, 1.4) for d in range(4)}
        self.powerup_timers = {d: random.uniform(4.0, 8.0) for d in range(4)}

        self.elapsed = 0.0
        self.score = 0.0
        self.coins_collected = 0
        self.scroll_speed = BASE_SCROLL_SPEED
        self.bg_scroll = 0.0
        self.new_high = False
        self.combo_flash = 0.0

    def start_game(self):
        self.reset()
        self.state = Game.PLAYING

    # ---------------- input ----------------
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.quit()
        elif e.type == pygame.KEYDOWN:
            if self.state == Game.MENU:
                if e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.start_game()
            elif self.state == Game.PLAYING:
                if e.key == pygame.K_SPACE:
                    self.player.jump()
                elif e.key == pygame.K_d:
                    self.try_switch_dimension()
                elif e.key in (pygame.K_p, pygame.K_ESCAPE):
                    self.state = Game.PAUSED
            elif self.state == Game.PAUSED:
                if e.key in (pygame.K_p, pygame.K_ESCAPE):
                    self.state = Game.PLAYING
                elif e.key == pygame.K_RETURN:
                    self.state = Game.MENU
            elif self.state == Game.GAME_OVER:
                if e.key == pygame.K_RETURN:
                    self.start_game()
        elif e.type == pygame.MOUSEBUTTONDOWN and self.state == Game.GAME_OVER:
            if self.restart_button_rect.collidepoint(e.pos):
                self.start_game()

    def try_switch_dimension(self):
        if self.switch_cooldown <= 0:
            old = self.dimension
            self.dimension = (self.dimension + 1) % 4
            self.switch_cooldown = DIMENSION_SWITCH_COOLDOWN
            self.transition_timer = 0.25
            col = DIMENSIONS[self.dimension]["accent"]
            self.particles.burst(self.player.x + self.player.w / 2, self.player.y + self.player.h / 2,
                                  col, count=26, speed=260, life=0.5)

    # ---------------- update ----------------
    def update(self, dt):
        if self.state != Game.PLAYING:
            return

        self.elapsed += dt
        self.scroll_speed = min(MAX_SCROLL_SPEED, BASE_SCROLL_SPEED + self.elapsed * SPEED_RAMP_PER_SEC * 10)
        self.bg_scroll += self.scroll_speed * dt

        if self.switch_cooldown > 0:
            self.switch_cooldown -= dt
        if self.transition_timer > 0:
            self.transition_timer -= dt

        keys = pygame.key.get_pressed()
        move_dir = 0
        if keys[pygame.K_LEFT]:
            move_dir -= 1
        if keys[pygame.K_RIGHT]:
            move_dir += 1

        self.player.update(dt, self.dimension, move_dir)
        self.particles.update(dt)

        # --- update all 4 dimensions' timelines ---
        for d in range(4):
            self.update_dimension_track(d, dt)

        # --- collisions only for the ACTIVE dimension ---
        self.check_collisions()

        # score
        self.score += self.scroll_speed * dt * 0.02
        if self.combo_flash > 0:
            self.combo_flash -= dt

        if self.player.lives <= 0:
            self.end_game()

    def update_dimension_track(self, d, dt):
        templates = OBSTACLE_TEMPLATES[d]

        # spawn obstacles
        self.spawn_timers[d] -= dt
        if self.spawn_timers[d] <= 0:
            template = random.choice(templates)
            self.obstacles[d].append(Obstacle(d, template, self.scroll_speed))
            difficulty_factor = clamp(1.4 - self.elapsed / 90.0, 0.55, 1.4)
            self.spawn_timers[d] = random.uniform(0.9, 1.7) * difficulty_factor

        # spawn coins
        self.coin_timers[d] -= dt
        if self.coin_timers[d] <= 0:
            self.coins[d].append(Coin(d, self.scroll_speed))
            self.coin_timers[d] = random.uniform(0.5, 1.1)

        # spawn power-ups
        self.powerup_timers[d] -= dt
        if self.powerup_timers[d] <= 0:
            self.powerups[d].append(PowerUp(d, self.scroll_speed))
            self.powerup_timers[d] = random.uniform(9.0, 16.0)

        magnet_target = None
        if d == self.dimension and self.player.magnet_timer > 0:
            magnet_target = (self.player.x + self.player.w / 2, self.player.y + self.player.h / 2)

        for o in self.obstacles[d]:
            o.update(dt, self.scroll_speed)
        for c in self.coins[d]:
            c.update(dt, self.scroll_speed, magnet_target)
        for p in self.powerups[d]:
            p.update(dt, self.scroll_speed)

        self.obstacles[d] = [o for o in self.obstacles[d] if o.alive]
        self.coins[d] = [c for c in self.coins[d] if c.alive]
        self.powerups[d] = [p for p in self.powerups[d] if p.alive]

    def check_collisions(self):
        d = self.dimension
        prect = self.player.rect

        for o in self.obstacles[d]:
            if o.alive and prect.colliderect(o.rect):
                hurt = self.player.hit(self.particles)
                o.alive = False
                if hurt:
                    self.combo_flash = 0.3

        for c in self.coins[d][:]:
            if prect.colliderect(c.rect):
                c.alive = False
                self.coins_collected += 1
                self.score += 25
                self.particles.emit(c.x, c.y, (255, 215, 0), 0, -40, 0.4, 3)

        for p in self.powerups[d][:]:
            if prect.colliderect(p.rect):
                p.alive = False
                self.apply_powerup(p.type)

        self.coins[d] = [c for c in self.coins[d] if c.alive]
        self.powerups[d] = [p for p in self.powerups[d] if p.alive]

    def apply_powerup(self, kind):
        col = DIMENSIONS[self.dimension]["accent"]
        self.particles.burst(self.player.x + self.player.w / 2, self.player.y, col, 18, 200)
        if kind == "shield":
            self.player.shield = True
        elif kind == "magnet":
            self.player.magnet_timer = 6.0
        elif kind == "boost":
            self.player.boost_timer = 5.0

    def end_game(self):
        self.state = Game.GAME_OVER
        final = int(self.score)
        if final > self.highscore:
            self.highscore = final
            self.new_high = True
            save_highscore(self.highscore)

    def quit(self):
        pygame.quit()
        raise SystemExit

    # ---------------- drawing ----------------
    def draw(self):
        if self.state == Game.MENU:
            self.draw_menu()
        else:
            self.draw_world()
            if self.state == Game.PAUSED:
                self.draw_pause_overlay()
            elif self.state == Game.GAME_OVER:
                self.draw_gameover_overlay()
        pygame.display.flip()

    def draw_background(self):
        info = DIMENSIONS[self.dimension]
        draw_vertical_gradient(self.screen, (0, 0, WIDTH, GROUND_Y), info["sky_top"], info["sky_bottom"])

        # dimension-flavored background decoration
        offset = self.bg_scroll % 200
        if self.dimension == EARTH:
            for i in range(-1, 6):
                x = i * 200 - offset
                pygame.draw.circle(self.screen, (255, 255, 255), (int(x), 90), 26)
                pygame.draw.circle(self.screen, (255, 255, 255), (int(x + 30), 100), 20)
        elif self.dimension == FIRE:
            for i in range(-1, 10):
                x = (i * 90 - offset * 1.4) % (WIDTH + 100) - 50
                h = 30 + (i * 37) % 40
                pygame.draw.polygon(self.screen, (255, 90, 0), [(x, GROUND_Y), (x + 12, GROUND_Y - h), (x + 24, GROUND_Y)])
        elif self.dimension == ICE:
            offset2 = self.bg_scroll * 0.6 % 200
            random.seed(1)
            for i in range(30):
                x = (i * 61 - offset2 * (1 + i % 3) * 0.5) % WIDTH
                y = (i * 53) % (GROUND_Y - 40) + 10
                pygame.draw.circle(self.screen, (255, 255, 255), (int(x), int(y)), 2)
        else:  # SPACE
            random.seed(7)
            for i in range(60):
                x = (i * 47 - self.bg_scroll * (0.2 + (i % 5) * 0.05)) % WIDTH
                y = (i * 31) % GROUND_Y
                size = 1 + (i % 3)
                pygame.draw.circle(self.screen, (255, 255, 255), (int(x), int(y)), size)

        # ground
        pygame.draw.rect(self.screen, info["ground"], (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
        stripe_off = int(self.bg_scroll) % 40
        for x in range(-40, WIDTH + 40, 40):
            pygame.draw.line(self.screen, info["ground2"], (x - stripe_off, GROUND_Y), (x - stripe_off - 18, HEIGHT), 3)
        pygame.draw.line(self.screen, info["accent"], (0, GROUND_Y), (WIDTH, GROUND_Y), 3)

        # transition flash
        if self.transition_timer > 0:
            alpha = int(180 * (self.transition_timer / 0.25))
            flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash.fill((*info["accent"], alpha))
            self.screen.blit(flash, (0, 0))

    def draw_world(self):
        self.draw_background()
        d = self.dimension
        colors = DIMENSIONS[d]
        for o in self.obstacles[d]:
            o.draw(self.screen, colors)
        for c in self.coins[d]:
            c.draw(self.screen)
        for p in self.powerups[d]:
            p.draw(self.screen)
        self.particles.draw(self.screen)
        self.player.draw(self.screen, d)
        self.draw_hud()

    def draw_hud(self):
        info = DIMENSIONS[self.dimension]
        # dimension indicator panel
        panel = pygame.Rect(16, 14, 230, 46)
        s = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 0, 0, 130), (0, 0, panel.w, panel.h), border_radius=10)
        self.screen.blit(s, panel.topleft)
        pygame.draw.rect(self.screen, info["accent"], panel, 3, border_radius=10)
        badge = pygame.Rect(panel.x + 8, panel.y + 8, 30, 30)
        pygame.draw.rect(self.screen, info["accent"], badge, border_radius=8)
        sym = self.font_med.render(info["symbol"], True, (20, 20, 20))
        self.screen.blit(sym, (badge.centerx - sym.get_width() / 2, badge.centery - sym.get_height() / 2))
        name_text = self.font_med.render(info["name"].upper(), True, (255, 255, 255))
        self.screen.blit(name_text, (badge.right + 10, panel.y + 8))
        hint = self.font_small.render("D to switch", True, (220, 220, 220))
        self.screen.blit(hint, (badge.right + 10, panel.y + 26))

        # dimension pips (next dimensions row)
        for i in range(4):
            di = DIMENSIONS[i]
            cx = 20 + i * 26
            cy = 70
            active = (i == self.dimension)
            r = 9 if active else 6
            pygame.draw.circle(self.screen, di["accent"], (cx, cy), r)
            if active:
                pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), r + 3, 2)

        # score / coins
        score_text = self.font_med.render(f"Score: {int(self.score)}", True, (255, 255, 255))
        self.screen.blit(score_text, (WIDTH - score_text.get_width() - 20, 16))
        coin_text = self.font_small.render(f"Coins: {self.coins_collected}", True, (255, 215, 0))
        self.screen.blit(coin_text, (WIDTH - coin_text.get_width() - 20, 48))
        hs_text = self.font_small.render(f"Best: {int(self.highscore)}", True, (220, 220, 220))
        self.screen.blit(hs_text, (WIDTH - hs_text.get_width() - 20, 68))

        # lives
        for i in range(3):
            color = (255, 60, 60) if i < self.player.lives else (70, 70, 70)
            pygame.draw.circle(self.screen, color, (20 + i * 26, 100 + 20), 8)

        # active buffs
        buff_x = 16
        buff_y = 130
        if self.player.shield:
            self.draw_buff_chip(buff_x, buff_y, "Shield", (100, 190, 255))
            buff_x += 100
        if self.player.magnet_timer > 0:
            self.draw_buff_chip(buff_x, buff_y, f"Magnet {self.player.magnet_timer:0.1f}", (255, 100, 200))
            buff_x += 130
        if self.player.boost_timer > 0:
            self.draw_buff_chip(buff_x, buff_y, f"Boost {self.player.boost_timer:0.1f}", (255, 200, 60))

    def draw_buff_chip(self, x, y, text, color):
        t = self.font_small.render(text, True, (20, 20, 20))
        pad = 8
        rect = pygame.Rect(x, y, t.get_width() + pad * 2, t.get_height() + 6)
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        self.screen.blit(t, (x + pad, y + 3))

    def draw_menu(self):
        info = DIMENSIONS[int(self.elapsed * 0.6) % 4]
        draw_vertical_gradient(self.screen, (0, 0, WIDTH, HEIGHT), info["sky_top"], info["sky_bottom"])
        self.elapsed += 1 / FPS

        title = self.font_title.render("DIMENSION RUNNER", True, (255, 255, 255))
        shadow = self.font_title.render("DIMENSION RUNNER", True, (0, 0, 0))
        self.screen.blit(shadow, (WIDTH / 2 - title.get_width() / 2 + 4, 124))
        self.screen.blit(title, (WIDTH / 2 - title.get_width() / 2, 120))

        sub = self.font_med.render("Switch dimensions. Dodge everything. Survive.", True, (255, 255, 255))
        self.screen.blit(sub, (WIDTH / 2 - sub.get_width() / 2, 200))

        for i, di in enumerate(DIMENSIONS):
            x = WIDTH / 2 - 260 + i * 140
            y = 280
            pygame.draw.circle(self.screen, di["accent"], (int(x), y), 34)
            t = self.font_small.render(di["name"], True, (255, 255, 255))
            self.screen.blit(t, (x - t.get_width() / 2, y + 44))

        controls = [
            "LEFT / RIGHT - Move      SPACE - Jump",
            "D - Switch Dimension      P - Pause",
        ]
        for i, line in enumerate(controls):
            t = self.font_small.render(line, True, (255, 255, 255))
            self.screen.blit(t, (WIDTH / 2 - t.get_width() / 2, 380 + i * 26))

        hs = self.font_med.render(f"High Score: {int(self.highscore)}", True, (255, 230, 120))
        self.screen.blit(hs, (WIDTH / 2 - hs.get_width() / 2, 450))

        prompt = self.font_med.render("Press ENTER or SPACE to start", True, (255, 255, 255))
        if int(self.elapsed * 2) % 2 == 0:
            self.screen.blit(prompt, (WIDTH / 2 - prompt.get_width() / 2, 510))

    def draw_pause_overlay(self):
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        s.fill((0, 0, 0, 150))
        self.screen.blit(s, (0, 0))
        t = self.font_big.render("PAUSED", True, (255, 255, 255))
        self.screen.blit(t, (WIDTH / 2 - t.get_width() / 2, HEIGHT / 2 - 80))
        t2 = self.font_small.render("P / ESC to resume    ENTER for main menu", True, (230, 230, 230))
        self.screen.blit(t2, (WIDTH / 2 - t2.get_width() / 2, HEIGHT / 2))

    def draw_gameover_overlay(self):
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        s.fill((0, 0, 0, 170))
        self.screen.blit(s, (0, 0))

        t = self.font_big.render("GAME OVER", True, (255, 90, 90))
        self.screen.blit(t, (WIDTH / 2 - t.get_width() / 2, 110))

        score_t = self.font_med.render(f"Score: {int(self.score)}", True, (255, 255, 255))
        self.screen.blit(score_t, (WIDTH / 2 - score_t.get_width() / 2, 190))

        if self.new_high:
            hs_t = self.font_med.render("NEW HIGH SCORE!", True, (255, 230, 120))
            self.screen.blit(hs_t, (WIDTH / 2 - hs_t.get_width() / 2, 230))
        else:
            hs_t = self.font_small.render(f"High Score: {int(self.highscore)}", True, (230, 230, 230))
            self.screen.blit(hs_t, (WIDTH / 2 - hs_t.get_width() / 2, 234))

        coins_t = self.font_small.render(f"Coins collected: {self.coins_collected}", True, (255, 215, 0))
        self.screen.blit(coins_t, (WIDTH / 2 - coins_t.get_width() / 2, 268))

        btn_w, btn_h = 220, 56
        self.restart_button_rect = pygame.Rect(WIDTH / 2 - btn_w / 2, 330, btn_w, btn_h)
        mouse_over = self.restart_button_rect.collidepoint(pygame.mouse.get_pos())
        color = (90, 200, 110) if mouse_over else (60, 160, 80)
        pygame.draw.rect(self.screen, color, self.restart_button_rect, border_radius=12)
        pygame.draw.rect(self.screen, (255, 255, 255), self.restart_button_rect, 2, border_radius=12)
        btn_t = self.font_med.render("RESTART", True, (255, 255, 255))
        self.screen.blit(btn_t, (self.restart_button_rect.centerx - btn_t.get_width() / 2,
                                  self.restart_button_rect.centery - btn_t.get_height() / 2))

        hint = self.font_small.render("Press ENTER or click RESTART", True, (220, 220, 220))
        self.screen.blit(hint, (WIDTH / 2 - hint.get_width() / 2, 400))

    # ---------------- main loop ----------------
    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.05)
            for e in pygame.event.get():
                self.handle_event(e)
            self.update(dt)
            self.draw()


if __name__ == "__main__":
    Game().run()