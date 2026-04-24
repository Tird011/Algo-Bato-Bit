"""

This is the ONLY file that imports pygame.
All logic lives in engine/ modules.

Enemy sprites → NONE (shapes + notation text, intentional aesthetic)
Player sprites → assets/sprites/player/idle.png, attack.png, hurt.png
UI sprites     → assets/sprites/ui/marker.png, combo_block.png

Controls:
  J → Zone 0 (O(1))
  K → Zone 1 (O(log n))
  L → Zone 2 (O(n) / O(n²))
  ESC → Quit
"""

import pygame
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine"))
from complexity_engine import ComplexityEngine, COMPLEXITY_MAP
from queue             import EnemyQueue, QueueConfig
from player            import Player, PlayerConfig
from execution_bar     import ExecutionBar, BarConfig
from hud               import HUD



SCREEN_W, SCREEN_H = 960, 540
FPS                = 60
TITLE              = "ALGO BATO BIT"

ASSETS_DIR         = os.path.join(os.path.dirname(__file__), "assets")
SPRITES_DIR        = os.path.join(ASSETS_DIR, "sprites")
AUDIO_DIR          = os.path.join(ASSETS_DIR, "audio")
FONTS_DIR          = os.path.join(ASSETS_DIR, "fonts")

# Yellowpad notebook aesthetic
C_BG        = (232, 220, 180)   # warm yellow paper
C_LINE      = (180, 190, 210)   # faint ruled lines (blue)
C_MARGIN    = (210,  80,  80)   # red margin line
C_INK       = ( 20,  20,  40)   # ballpen ink (near-black, slight blue)
C_INK_FAINT = (120, 130, 150)   # lighter ink for secondary text

# Complexity colors — same as engine
C_ZONE = {
    0: (  0, 200, 190),   # O(1)    cyan
    1: (230, 200,   0),   # O(log n) yellow
    2: (200,   0, 130),   # O(n)    magenta
}
C_BOSS      = (210,  40,  40)   # O(n²)  red
C_HIT_GOOD  = ( 60, 220, 100)
C_HIT_BAD   = (220,  60,  60)
C_WHITE     = (255, 255, 255)

BAR_Y        = SCREEN_H - 100
BAR_H        = 52
BAR_X        = 60
BAR_W        = SCREEN_W - 120
ENEMY_LANE_Y = 100
PLAYER_X     = 80
PLAYER_Y     = 260
COMBO_X      = 20
COMBO_Y      = 160



def load_sprite(path: str, size: tuple) -> pygame.Surface:
    """Load a sprite or return a colored placeholder if missing."""
    if os.path.exists(path):
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.scale(img, size)
    # Placeholder — visible box so you know the slot is empty
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    pygame.draw.rect(surf, C_INK, (0, 0, *size), 2)
    pygame.draw.line(surf, C_INK, (0, 0), size, 1)
    pygame.draw.line(surf, C_INK, (size[0], 0), (0, size[1]), 1)
    return surf


def load_font(name: str, size: int) -> pygame.font.Font:
    path = os.path.join(FONTS_DIR, name)
    if os.path.exists(path):
        return pygame.font.Font(path, size)
    return pygame.font.SysFont("Courier", size, bold=True)



class Game:
    def __init__(self, screen: pygame.Surface):
        self.screen  = screen
        self.clock   = pygame.time.Clock()
        self.running = True

        self.engine = ComplexityEngine()
        self.queue  = EnemyQueue(
            self.engine,
            QueueConfig(front_target_x=PLAYER_X + 140),
        )
        self.player = Player(PlayerConfig(x=PLAYER_X, y=PLAYER_Y))
        self.bar    = ExecutionBar(BarConfig(x=BAR_X, width=BAR_W))
        self.hud    = HUD(max_memory=self.player.cfg.max_health)

        self.font_lg  = load_font("font_main.ttf", 28)
        self.font_md  = load_font("font_main.ttf", 18)
        self.font_sm  = load_font("font_main.ttf", 13)

        sprite_path = lambda name: os.path.join(SPRITES_DIR, "player", name)
        self.player_sprites = {
            "idle":   load_sprite(sprite_path("idle.png"),   (80, 80)),
            "attack": load_sprite(sprite_path("attack.png"), (80, 80)),
            "hurt":   load_sprite(sprite_path("hurt.png"),   (80, 80)),
            "dead":   load_sprite(sprite_path("hurt.png"),   (80, 80)),
        }

        ui_path = lambda name: os.path.join(SPRITES_DIR, "ui", name)
        self.marker_sprite      = load_sprite(ui_path("marker.png"),      (12, BAR_H + 8))
        self.combo_block_sprite = load_sprite(ui_path("combo_block.png"), (18, 12))

        bg_path = os.path.join(ASSETS_DIR, "YellowPad.jpg")
        if os.path.exists(bg_path):
            raw = pygame.image.load(bg_path).convert()
            self.bg = pygame.transform.scale(raw, (SCREEN_W, SCREEN_H))
        else:
            self.bg = None

        self._diff_timer = 0.0


    def run(self):
        while self.running:
            dt_ms = self.clock.tick(FPS)
            self._handle_events()
            self._update(dt_ms)
            self._draw()


    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key in (pygame.K_j, pygame.K_k, pygame.K_l):
                    self._handle_input(event.key)

    def _handle_input(self, key: int):
        if self.player.is_dead:
            return

        zone_map = {pygame.K_j: 0, pygame.K_k: 1, pygame.K_l: 2}
        pressed_zone = zone_map[key]

        # Get tolerance from front enemy (boss = tighter window)
        front     = self.queue.front
        tolerance = front.tolerance if front else 0.72
        marker_ok = self.bar.marker_in_window(pressed_zone, tolerance)

        # Resolve through queue → engine
        q_events = self.queue.handle_input(pressed_zone, marker_ok)
        for e in q_events:
            if e.kind == "HIT_RESULT":
                p_events = self.player.react_to_hit(e.hit_result)
                self.bar.trigger_flash(pressed_zone, e.hit_result.success)

                if e.hit_result.success:
                    pts = int(e.hit_result.points * self.player.score_multiplier)
                    self.hud.add_score(pts)
                    self.bar.on_hit(self.player.combo)
                    self.hud.set_feedback(e.hit_result.feedback, 700)
                else:
                    self.bar.on_miss()
                    self.hud.set_feedback(e.hit_result.feedback, 900)


    def _update(self, dt_ms: float):
        if self.player.is_dead:
            self._handle_death(dt_ms)
            return

        # Queue
        q_events = self.queue.update(dt_ms)
        for e in q_events:
            if e.kind == "AUTO_MISS":
                p_events = self.player.take_damage(is_boss=e.is_boss)
                self.bar.on_miss()
                self.hud.set_feedback("MISSED!", 600)
                for pe in p_events:
                    if pe.kind == "DEAD":
                        self.hud.set_feedback("SEGFAULT. MEMORY FULL.", 3000)

        # Player state machine tick
        self.player.update(dt_ms)

        # Bar
        self.bar.update(dt_ms)

        # HUD sync
        self.hud.update(dt_ms)
        self.hud.sync_player(self.player)
        self.hud.sync_queue(self.queue)

        # Difficulty scaling every 5 seconds
        self._diff_timer += dt_ms
        if self._diff_timer >= 5000:
            self._diff_timer = 0
            self.queue.scale_difficulty(self.hud.score)

    def _handle_death(self, dt_ms: float):
        """Freeze everything, let feedback linger, then restart."""
        self.hud.update(dt_ms)
        if self.hud.feedback_timer <= 0:
            self._restart()

    def _restart(self):
        self.queue.reset()
        self.player.reset()
        self.bar.reset()
        self.hud.reset()
        self._diff_timer = 0.0


    def _draw(self):
        # Background
        if self.bg:
            self.screen.blit(self.bg, (0, 0))
        else:
            self.screen.fill(C_BG)
            self._draw_ruled_lines()

        self._draw_margin_line()
        self._draw_enemies()
        self._draw_player()
        self._draw_bar()
        self._draw_hud()
        self._draw_combo_stack()
        self._draw_dsa_labels()

        pygame.display.flip()

    def _draw_ruled_lines(self):
        """Fallback notebook lines if no bg image."""
        for y in range(40, SCREEN_H, 28):
            pygame.draw.line(self.screen, C_LINE, (0, y), (SCREEN_W, y), 1)

    def _draw_margin_line(self):
        pygame.draw.line(self.screen, C_MARGIN, (55, 0), (55, SCREEN_H), 2)


    def _draw_enemies(self):
        for enemy in self.queue.all_enemies:
            self._draw_enemy(enemy)

    def _draw_enemy(self, enemy):
        data     = COMPLEXITY_MAP[enemy.complexity]
        color    = C_BOSS if enemy.is_boss else C_ZONE.get(data["zones"][0], C_INK)
        ex       = int(enemy.x)
        ey       = int(ENEMY_LANE_Y + enemy.wobble)
        size     = 58 if enemy.is_boss else 48

        # Body — filled rectangle with ink border (MS Paint rough style)
        body_rect = pygame.Rect(ex, ey, size, size)
        pygame.draw.rect(self.screen, color,  body_rect)
        pygame.draw.rect(self.screen, C_INK,  body_rect, 3)

        # Complexity label centered on body
        label     = self.font_sm.render(enemy.complexity, True, C_INK)
        lx        = ex + size // 2 - label.get_width() // 2
        ly        = ey + size // 2 - label.get_height() // 2
        self.screen.blit(label, (lx, ly))

        # Boss indicator — extra border ring
        if enemy.is_boss:
            pygame.draw.rect(self.screen, C_BOSS,
                             body_rect.inflate(6, 6), 2)

        # "Waiting" pulse — dim ring when enemy is at front holding position
        if enemy.state == "waiting":
            pygame.draw.rect(self.screen, C_WHITE,
                             body_rect.inflate(10, 10), 1)


    def _draw_player(self):
        state  = self.player.state if self.player.state in self.player_sprites else "idle"
        sprite = self.player_sprites[state]
        px     = int(self.player.x)
        py     = int(self.player.y + self.player.wobble)
        self.screen.blit(sprite, (px, py))


    def _draw_bar(self):
        bar_rect = pygame.Rect(BAR_X, BAR_Y, BAR_W, BAR_H)

        # Zone backgrounds
        for i in range(3):
            zx        = int(self.bar.zone_x(i))
            zw        = int(self.bar.zone_width)
            base_col  = C_ZONE[i]
            intensity = self.bar.flash_intensity(i)

            if intensity > 0:
                # Lerp toward hit/miss flash color
                front   = self.queue.front
                success = front is None or front.required_zone != i
                flash_c = C_HIT_GOOD if success else C_HIT_BAD
                color   = self._lerp_color(base_col, flash_c, intensity)
            else:
                color = base_col

            zone_rect = pygame.Rect(zx, BAR_Y, zw, BAR_H)
            # Semi-transparent fill — draw on a temp surface
            zone_surf = pygame.Surface((zw, BAR_H), pygame.SRCALPHA)
            zone_surf.fill((*color, 160))
            self.screen.blit(zone_surf, (zx, BAR_Y))
            pygame.draw.rect(self.screen, C_INK, zone_rect, 2)

            # Zone key label
            key_label = self.font_sm.render(["J", "K", "L"][i], True, C_INK)
            self.screen.blit(key_label, (zx + 6, BAR_Y + 4))

            # Zone complexity label
            comp_label = self.font_sm.render(self.bar.ZONE_KEYS[i], True, C_INK)
            cx = zx + zw // 2 - comp_label.get_width() // 2
            self.screen.blit(comp_label, (cx, BAR_Y + BAR_H - 18))

        # Outer bar border
        pygame.draw.rect(self.screen, C_INK, bar_rect, 3)

        # Marker
        mx = int(self.bar.marker_x) - self.marker_sprite.get_width() // 2
        self.screen.blit(self.marker_sprite,
                         (mx, BAR_Y - 4))


    def _draw_hud(self):
        # Score
        score_surf = self.font_lg.render(f"{self.hud.score:06d}", True, C_INK)
        self.screen.blit(score_surf, (SCREEN_W - score_surf.get_width() - 20, 16))

        hi_surf = self.font_sm.render(f"HI {self.hud.high_score:06d}", True, C_INK_FAINT)
        self.screen.blit(hi_surf, (SCREEN_W - hi_surf.get_width() - 20, 48))

        # Memory bar (health)
        mem_label = self.font_sm.render("MEMORY", True, C_INK)
        self.screen.blit(mem_label, (BAR_X, BAR_Y - 36))

        mem_w     = int((self.player.health_pct) * 200)
        mem_rect  = pygame.Rect(BAR_X + 70, BAR_Y - 34, 200, 14)
        fill_rect = pygame.Rect(BAR_X + 70, BAR_Y - 34, max(mem_w, 0), 14)
        mem_color = C_HIT_GOOD if self.player.health_pct > 0.4 else C_HIT_BAD
        pygame.draw.rect(self.screen, C_INK,     mem_rect,  2)
        pygame.draw.rect(self.screen, mem_color, fill_rect)

        # Multiplier
        if self.hud.multiplier > 1.0:
            mult_surf = self.font_md.render(
                f"x{self.hud.multiplier:.1f}", True, C_ZONE[1])
            self.screen.blit(mult_surf, (BAR_X, BAR_Y - 58))

        # Feedback text — center screen
        if self.hud.feedback:
            alpha    = min(self.hud.feedback_timer / 200.0, 1.0)
            fb_surf  = self.font_lg.render(self.hud.feedback, True, C_INK)
            fx       = SCREEN_W // 2 - fb_surf.get_width() // 2
            fy       = SCREEN_H // 2 - 60
            self.screen.blit(fb_surf, (fx, fy))

        # Accuracy
        acc_surf = self.font_sm.render(
            f"ACC {self.hud.accuracy:.0%}", True, C_INK_FAINT)
        self.screen.blit(acc_surf, (BAR_X, 16))


    def _draw_combo_stack(self):
        """
        Draws the combo stack as literal stacked blocks growing upward.
        Each block is colored by the enemy type that was defeated.
        This makes the Stack DSA visible in gameplay.
        """
        items     = self.player.combo_stack.items
        block_h   = 14
        block_w   = 22
        stack_top = PLAYER_Y - 10   # blocks grow upward from player

        # Label
        label = self.font_sm.render("STACK", True, C_INK_FAINT)
        self.screen.blit(label, (COMBO_X, stack_top - len(items) * block_h - 20))

        for i, enemy_type in enumerate(items):
            data  = COMPLEXITY_MAP[enemy_type]
            color = C_BOSS if data["is_boss"] else C_ZONE.get(data["zones"][0], C_INK)
            by    = stack_top - (i + 1) * block_h
            brect = pygame.Rect(COMBO_X, by, block_w, block_h - 2)
            pygame.draw.rect(self.screen, color, brect)
            pygame.draw.rect(self.screen, C_INK,  brect, 1)

        # Stack size label
        if items:
            sz = self.font_sm.render(f"{len(items)}", True, C_INK)
            self.screen.blit(sz, (COMBO_X + block_w + 4,
                                  stack_top - len(items) * block_h))

    # ── DSA education labels ───────────────────────────────────────────────────

    def _draw_dsa_labels(self):
        """
        Small labels that name the data structures in use.
        Subtle but present — teaches while playing.
        """
        q_surf = self.font_sm.render(self.hud.dsa_label,   True, C_INK_FAINT)
        s_surf = self.font_sm.render(self.hud.stack_label, True, C_INK_FAINT)
        self.screen.blit(q_surf, (70, SCREEN_H - 28))
        self.screen.blit(s_surf, (70, SCREEN_H - 14))

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _lerp_color(a: tuple, b: tuple, t: float) -> tuple:
        return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

def main():
    pygame.init()
    pygame.display.set_caption(TITLE)
    os.makedirs(os.path.join(ASSETS_DIR, "sprites", "player"), exist_ok=True)
    os.makedirs(os.path.join(ASSETS_DIR, "sprites", "ui"),     exist_ok=True)
    os.makedirs(os.path.join(ASSETS_DIR, "audio", "sfx"),      exist_ok=True)
    os.makedirs(os.path.join(ASSETS_DIR, "audio", "music"),    exist_ok=True)
    os.makedirs(FONTS_DIR, exist_ok=True)

    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    game   = Game(screen)
    game.run()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()