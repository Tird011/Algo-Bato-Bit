"""
╔══════════════════════════════════════════════════════════╗
║           ALGO BATO BIT — Digital Prototype              ║
║           Rhythm / Logic Game · Pygame Base v1.0         ║ angas mag ascii
╚══════════════════════════════════════════════════════════╝

HOW TO RUN:
    pip install pygame
    python Prototype.py

ASSET SLOTS (drop files in ./assets/ to replace placeholders):
    enemy_o1.png        — O(1) enemy sprite   (64x64 recommended)
    enemy_on.png        — O(n) enemy sprite
    enemy_on2.png       — O(n²) enemy sprite
    enemy_ologn.png     — O(log n) enemy sprite
    bg_tile.png         — Background texture tile
    hit_marker.png      — The sliding cursor on the execution bar
    font_main.ttf       — hand-drawn / brutalist font


       _________________________________
 / \                                     \.
|   |   Testing sa ascii skills          |.
 \_ |                                    |.
    |  CONTROLS:                         |.
    |    J  — Hit Zone LEFT   → O(1)     |.
    |    K  — Hit Zone CENTER → O(log n) |.
    |    L  — Hit Zone RIGHT  → O(n)     |.
    |    ESC — Quit                      |.
    |                                    |.
    |                                    |.
    |                                    |.
    |                                    |.
    |                                    |.
    |                                    |.
    |                                    |.
    |                                    |.
    |                                    |.
    |                                    |.
    |   _________________________________|___
    |  /                                    /.
    \_/++__________________________________/.
This version is only a prototype ¯\_( ͡° ͜ʖ ͡°)_/¯
"""

import pygame
import random
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

SCREEN_W, SCREEN_H = 960, 540
FPS = 60
TITLE = "ALGO BATO BIT"

# Digital Brutalist palette — high contrast, dithered feel
C_BG         = (18,  18,  18)   # near-black background
C_PAPER      = (232, 220, 198)  # warm paper / MS Paint white
C_INK        = (10,  10,  10)   # sketch ink
C_RED        = (220,  40,  40)  # health / danger
C_CYAN       = ( 0,  210, 200)  # O(1) zone
C_YELLOW     = (240, 210,  0)   # O(log n) zone
C_MAGENTA    = (210,  0,  140)  # O(n) zone
C_GRID       = ( 40,  40,  40)  # background grid lines
C_HIT_GOOD   = ( 80, 255, 120)  # perfect hit flash
C_HIT_BAD    = (255,  60,  60)  # miss flash

# Execution Bar geometry
BAR_Y        = SCREEN_H - 90
BAR_H        = 52
BAR_MARGIN   = 60
BAR_W        = SCREEN_W - BAR_MARGIN * 2
ZONE_W       = BAR_W // 3

# Marker
MARKER_SPEED_BASE = 3.0   # pixels per frame; scales with score

# Enemy lane
ENEMY_Y      = 80
ENEMY_SPEED  = 1.8        # pixels per frame
SPAWN_INTERVAL = 2800     # ms between enemy spawns
QUEUE_SPACING = 110       # px between queued enemies on screen

# Memory (health)
MAX_MEMORY   = 100
LEAK_AMOUNT  = 20         # memory drained on miss / wrong zone

# Hit window (fraction of zone width the marker must be inside)
HIT_TOLERANCE = 0.72

# Complexity hierarchy: what BEATS what
# Player presses the CORRECT counter-complexity to defeat the enemy
COMPLEXITY_HIERARCHY = {
    "O(1)":     {"color": C_CYAN,    "key": pygame.K_j, "zone": 0, "weight": 35},
    "O(log n)": {"color": C_YELLOW,  "key": pygame.K_k, "zone": 1, "weight": 30},
    "O(n)":     {"color": C_MAGENTA, "key": pygame.K_l, "zone": 2, "weight": 25},
    "O(n²)":    {"color": C_RED,     "key": None,       "zone": 2, "weight": 10},
    # O(n²) enemies require zone 2 (O(n) counter) — hardest timing window
}

ENEMY_TYPES = list(COMPLEXITY_HIERARCHY.keys())
SPAWN_WEIGHTS = [COMPLEXITY_HIERARCHY[e]["weight"] for e in ENEMY_TYPES]

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


# ─── ASSET LOADER ─────────────────────────────────────────────────────────────

def load_image(filename: str, size: Optional[tuple] = None) -> pygame.Surface:
    """
    Tries to load from ./assets/<filename>.
    Falls back to a procedurally-drawn placeholder if file is missing.
    Uses nearest-neighbor scaling to preserve 'crunchy' pixel edges.
    """
    path = os.path.join(ASSETS_DIR, filename)
    if os.path.exists(path):
        img = pygame.image.load(path).convert_alpha()
        if size:
            img = pygame.transform.scale(img, size)  # nearest-neighbor in pygame default
        return img
    # ── Procedural placeholder ──
    w, h = size if size else (64, 64)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    # Sketchy border
    pygame.draw.rect(surf, C_PAPER, (0, 0, w, h))
    pygame.draw.rect(surf, C_INK, (0, 0, w, h), 3)
    # Diagonal cross — placeholder 'X'
    pygame.draw.line(surf, C_INK, (4, 4), (w - 4, h - 4), 2)
    pygame.draw.line(surf, C_INK, (w - 4, 4), (4, h - 4), 2)
    return surf


def load_font(filename: str, size: int) -> pygame.font.Font:
    path = os.path.join(ASSETS_DIR, filename)
    if os.path.exists(path):
        return pygame.font.Font(path, size)
    return pygame.font.SysFont("Courier", size, bold=True)


# ─── ENEMY ────────────────────────────────────────────────────────────────────

class Enemy:
    SIZE = (72, 72)

    def __init__(self, complexity: str, images: dict, x: float):
        self.complexity = complexity
        self.info       = COMPLEXITY_HIERARCHY[complexity]
        self.color      = self.info["color"]
        self.zone       = self.info["zone"]   # which hit-zone defeats it
        self.x          = x
        self.y          = float(ENEMY_Y)
        self.image      = images.get(complexity, load_image("placeholder.png", self.SIZE))
        self.alive      = True
        # Wobble animation state (hand-drawn jitter)
        self._wobble_t  = random.uniform(0, math.tau)

    def update(self, dt_ms: float):
        self.x -= ENEMY_SPEED * (dt_ms / 16.67)   # normalize to ~60fps
        self._wobble_t += 0.08

    @property
    def wobble_offset(self) -> float:
        return math.sin(self._wobble_t) * 3.0

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        draw_x = int(self.x)
        draw_y = int(self.y + self.wobble_offset)
        surface.blit(self.image, (draw_x, draw_y))
        # Complexity label under sprite — ink-stamp style
        label = font.render(self.complexity, True, self.color)
        lx = draw_x + self.SIZE[0] // 2 - label.get_width() // 2
        ly = draw_y + self.SIZE[1] + 4
        # Ink shadow for legibility
        shadow = font.render(self.complexity, True, C_INK)
        surface.blit(shadow, (lx + 2, ly + 2))
        surface.blit(label, (lx, ly))


# ─── EXECUTION BAR ────────────────────────────────────────────────────────────

class ExecutionBar:
    """
    Three hit zones (J / K / L).
    A marker bounces left↔right — player must press when marker is in
    the zone matching the front enemy's complexity.
    """

    ZONE_LABELS = ["O(1)", "O(log n)", "O(n)"]
    ZONE_COLORS = [C_CYAN, C_YELLOW, C_MAGENTA]
    ZONE_KEYS   = ["J", "K", "L"]

    def __init__(self):
        self.x          = float(BAR_MARGIN)   # marker x position
        self.direction  = 1                   # +1 right, -1 left
        self.speed      = MARKER_SPEED_BASE
        self.flash      = {}                  # zone_idx → (color, timer_ms)

    def update(self, dt_ms: float):
        self.x += self.direction * self.speed * (dt_ms / 16.67)
        if self.x >= BAR_MARGIN + BAR_W:
            self.x = float(BAR_MARGIN + BAR_W)
            self.direction = -1
        elif self.x <= BAR_MARGIN:
            self.x = float(BAR_MARGIN)
            self.direction = 1

        # Decay flash effects
        expired = [k for k, (_, t) in self.flash.items() if t <= 0]
        for k in expired:
            del self.flash[k]
        for k in list(self.flash):
            c, t = self.flash[k]
            self.flash[k] = (c, t - dt_ms)

    def marker_zone(self) -> int:
        """Returns 0/1/2 for which zone the marker is currently in."""
        rel = self.x - BAR_MARGIN
        return min(int(rel // ZONE_W), 2)

    def marker_in_zone(self, zone_idx: int) -> bool:
        """True if the marker centre is comfortably inside zone_idx."""
        zone_left  = BAR_MARGIN + zone_idx * ZONE_W
        zone_right = zone_left + ZONE_W
        margin     = ZONE_W * (1 - HIT_TOLERANCE) / 2
        return zone_left + margin <= self.x <= zone_right - margin

    def trigger_flash(self, zone_idx: int, success: bool):
        color = C_HIT_GOOD if success else C_HIT_BAD
        self.flash[zone_idx] = (color, 220)   # 220 ms flash

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        # ── Zone backgrounds ──
        for i, color in enumerate(self.ZONE_COLORS):
            zx = BAR_MARGIN + i * ZONE_W
            # Flash override
            if i in self.flash:
                draw_color = self.flash[i][0]
            else:
                draw_color = tuple(max(0, c - 170) for c in color)   # dim version

            pygame.draw.rect(surface, draw_color, (zx, BAR_Y, ZONE_W, BAR_H))
            pygame.draw.rect(surface, color, (zx, BAR_Y, ZONE_W, BAR_H), 2)

            # Key label
            key_label = font.render(f"[{self.ZONE_KEYS[i]}]", True, color)
            surface.blit(key_label, (zx + 6, BAR_Y + 4))

            # Complexity label
            cx_label = font.render(self.ZONE_LABELS[i], True, C_PAPER)
            cx_x = zx + ZONE_W // 2 - cx_label.get_width() // 2
            surface.blit(cx_label, (cx_x, BAR_Y + BAR_H - cx_label.get_height() - 4))

        # ── Outer border ──
        pygame.draw.rect(surface, C_PAPER, (BAR_MARGIN, BAR_Y, BAR_W, BAR_H), 3)

        # ── Marker ──
        mx = int(self.x)
        marker_h = BAR_H + 12
        marker_y = BAR_Y - 6
        pygame.draw.rect(surface, C_PAPER, (mx - 3, marker_y, 6, marker_h))
        pygame.draw.rect(surface, C_INK,   (mx - 3, marker_y, 6, marker_h), 1)
        # Arrow head
        pygame.draw.polygon(surface, C_PAPER, [
            (mx, marker_y - 8), (mx - 7, marker_y), (mx + 7, marker_y)
        ])


# ─── HUD ──────────────────────────────────────────────────────────────────────

class HUD:
    def __init__(self, font_large, font_small):
        self.font_large = font_large
        self.font_small = font_small

    def draw(self, surface: pygame.Surface, memory: float, score: int,
             streak: int, last_result: str):
        
        mem_label = self.font_small.render("MEMORY", True, C_PAPER)
        surface.blit(mem_label, (16, 14))

        bar_full_w = 200
        mem_ratio  = max(0, memory / MAX_MEMORY)
        mem_color  = C_HIT_GOOD if mem_ratio > 0.5 else C_YELLOW if mem_ratio > 0.25 else C_RED
        pygame.draw.rect(surface, C_GRID,    (16, 32, bar_full_w, 14))
        pygame.draw.rect(surface, mem_color, (16, 32, int(bar_full_w * mem_ratio), 14))
        pygame.draw.rect(surface, C_PAPER,   (16, 32, bar_full_w, 14), 2)

        mem_pct = self.font_small.render(f"{int(memory)}%", True, C_PAPER)
        surface.blit(mem_pct, (16 + bar_full_w + 8, 30))

        # ── Score (top-right) ──
        score_surf = self.font_large.render(f"{score:06d}", True, C_PAPER)
        surface.blit(score_surf, (SCREEN_W - score_surf.get_width() - 16, 10))

        # ── Streak ──
        if streak > 1:
            streak_color = C_YELLOW if streak < 5 else C_CYAN if streak < 10 else C_HIT_GOOD
            streak_surf = self.font_small.render(f"STREAK ×{streak}", True, streak_color)
            surface.blit(streak_surf, (SCREEN_W - streak_surf.get_width() - 16, 46))

        # ── Last result feedback ──
        if last_result:
            result_surf = self.font_large.render(last_result, True,
                          C_HIT_GOOD if "PERFECT" in last_result or "BEAT" in last_result
                          else C_RED)
            rx = SCREEN_W // 2 - result_surf.get_width() // 2
            surface.blit(result_surf, (rx, SCREEN_H // 2 - 60))


# ─── GAME ─────────────────────────────────────────────────────────────────────

class Game:
    def __init__(self, screen: pygame.Surface):
        self.screen  = screen
        self.clock   = pygame.time.Clock()
        self.running = True

        # Fonts
        self.font_large = load_font("font_main.ttf", 28)
        self.font_small = load_font("font_main.ttf", 16)

        # Enemy sprite images dict
        self.enemy_images = {
            "O(1)":     load_image("enemy_o1.png",    Enemy.SIZE),
            "O(log n)": load_image("enemy_ologn.png", Enemy.SIZE),
            "O(n)":     load_image("enemy_on.png",    Enemy.SIZE),
            "O(n²)":    load_image("enemy_on2.png",   Enemy.SIZE),
        }

        # Background tile (optional)
        self.bg_tile = load_image("bg_tile.png", (64, 64)) if \
            os.path.exists(os.path.join(ASSETS_DIR, "bg_tile.png")) else None

        # State
        self.enemy_queue: list[Enemy]  = []
        self.bar        = ExecutionBar()
        self.hud        = HUD(self.font_large, self.font_small)

        self.memory     = float(MAX_MEMORY)
        self.score      = 0
        self.streak     = 0
        self.last_result= ""
        self._result_timer = 0

        # Spawn timer
        self._spawn_timer = 0
        self._next_spawn  = SPAWN_INTERVAL

        # Queue entry X position for newly spawned enemies
        self._queue_entry_x = float(SCREEN_W + 20)

    # ── Spawning ──────────────────────────────────────────────────────────────

    def _spawn_enemy(self):
        complexity = random.choices(ENEMY_TYPES, weights=SPAWN_WEIGHTS, k=1)[0]
        # Position: right-most slot in the visible queue
        x = self._queue_entry_x
        self.enemy_queue.append(Enemy(complexity, self.enemy_images, x))

    # ── Input ─────────────────────────────────────────────────────────────────

    def _handle_key(self, key: int):
        """Called when player presses J/K/L."""
        zone_map = {pygame.K_j: 0, pygame.K_k: 1, pygame.K_l: 2}
        if key not in zone_map:
            return
        pressed_zone = zone_map[key]

        if not self.enemy_queue:
            return

        front = self.enemy_queue[0]
        correct_zone = front.zone
        marker_ok    = self.bar.marker_in_zone(pressed_zone)

        if pressed_zone == correct_zone and marker_ok:
            # ✅ Perfect hit
            self.streak += 1
            points = 100 * self.streak
            self.score += points
            self.last_result = f"BEAT! +{points}"
            self._result_timer = 700
            self.bar.trigger_flash(pressed_zone, success=True)
            front.alive = False
            self.enemy_queue.pop(0)
            # Speed up slightly on streak
            self.bar.speed = MARKER_SPEED_BASE + min(self.streak * 0.15, 3.5)
        else:
            # ❌ Miss or wrong zone
            self.streak = 0
            self.memory -= LEAK_AMOUNT
            self.last_result = "MEMORY LEAK!"
            self._result_timer = 900
            self.bar.trigger_flash(pressed_zone, success=False)
            if self.memory <= 0:
                self.memory = 0
                self._game_over()

    def _game_over(self):
        self.last_result = "SEGFAULT"
        self._result_timer = 3000
        # Simple: restart state after a pause (could show a death screen)
        pygame.time.set_timer(pygame.USEREVENT + 1, 3000)

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt_ms: float):
        # Spawn
        self._spawn_timer += dt_ms
        if self._spawn_timer >= self._next_spawn:
            self._spawn_timer = 0
            self._next_spawn  = random.randint(int(SPAWN_INTERVAL * 0.8),
                                               int(SPAWN_INTERVAL * 1.3))
            self._spawn_enemy()

        # Move enemies
        for enemy in self.enemy_queue:
            enemy.update(dt_ms)

        # Reposition queue enemies so they don't overlap
        # Front enemy targets a fixed "approach" X; others trail behind
        FRONT_TARGET_X = BAR_MARGIN + 30
        if self.enemy_queue:
            self.enemy_queue[0].x = max(self.enemy_queue[0].x,
                                        FRONT_TARGET_X - 1)  # stop at front
            for i in range(1, len(self.enemy_queue)):
                desired = self.enemy_queue[i - 1].x + QUEUE_SPACING
                # Move toward desired without overtaking
                self.enemy_queue[i].x = max(self.enemy_queue[i].x,
                                            self.enemy_queue[i - 1].x + QUEUE_SPACING)

        # If front enemy has passed the bar — auto-miss
        if self.enemy_queue and self.enemy_queue[0].x < BAR_MARGIN - Enemy.SIZE[0]:
            self.enemy_queue.pop(0)
            self.streak = 0
            self.memory -= LEAK_AMOUNT
            self.last_result = "MISSED!"
            self._result_timer = 600
            if self.memory <= 0:
                self._game_over()

        # Bar
        self.bar.update(dt_ms)

        # Result timer
        if self._result_timer > 0:
            self._result_timer -= dt_ms
            if self._result_timer <= 0:
                self.last_result = ""

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self):
        # Background
        self.screen.fill(C_BG)
        self._draw_background_grid()

        # Queue direction arrow hint
        self._draw_queue_lane()

        # Enemies
        for enemy in self.enemy_queue:
            enemy.draw(self.screen, self.font_small)

        # Execution bar
        self.bar.draw(self.screen, self.font_small)

        # HUD
        self.hud.draw(self.screen, self.memory, self.score,
                      self.streak, self.last_result if self._result_timer > 0 else "")

        pygame.display.flip()

    def _draw_background_grid(self):
        """Dithered / graph-paper feel."""
        spacing = 32
        for x in range(0, SCREEN_W, spacing):
            pygame.draw.line(self.screen, C_GRID, (x, 0), (x, SCREEN_H), 1)
        for y in range(0, SCREEN_H, spacing):
            pygame.draw.line(self.screen, C_GRID, (0, y), (SCREEN_W, y), 1)

    def _draw_queue_lane(self):
        """A horizontal guide-line for the enemy queue."""
        lane_y = ENEMY_Y + Enemy.SIZE[1] // 2
        pygame.draw.line(self.screen, C_GRID,
                         (BAR_MARGIN, lane_y), (SCREEN_W - BAR_MARGIN, lane_y), 2)
        # Arrow pointing left
        ax = BAR_MARGIN + 20
        pygame.draw.polygon(self.screen, C_GRID, [
            (ax, lane_y), (ax + 14, lane_y - 7), (ax + 14, lane_y + 7)
        ])
        label = self.font_small.render("EXECUTION QUEUE →→→", True, C_GRID)
        self.screen.blit(label, (SCREEN_W // 2 - label.get_width() // 2, ENEMY_Y - 22))

    # ── Main Loop ─────────────────────────────────────────────────────────────

    def run(self):
        while self.running:
            dt_ms = self.clock.tick(FPS)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    else:
                        self._handle_key(event.key)
                elif event.type == pygame.USEREVENT + 1:
                    # Restart after game-over
                    pygame.time.set_timer(pygame.USEREVENT + 1, 0)
                    self._restart()

            self.update(dt_ms)
            self.draw()

    def _restart(self):
        self.enemy_queue.clear()
        self.memory      = float(MAX_MEMORY)
        self.score       = 0
        self.streak      = 0
        self.last_result = ""
        self.bar.speed   = MARKER_SPEED_BASE
        self._spawn_timer = 0


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

def main():
    pygame.init()
    os.makedirs(ASSETS_DIR, exist_ok=True)

    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption(TITLE)

    # Optional: set a hand-drawn window icon if available
    icon_path = os.path.join(ASSETS_DIR, "icon.png")
    if os.path.exists(icon_path):
        pygame.display.set_icon(pygame.image.load(icon_path))

    game = Game(screen)
    game.run()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
