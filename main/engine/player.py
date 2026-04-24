"""

Owns everything about the player character:
  - Player          : state machine + health + position
  - ComboStack      : DSA stack implementation for combo tracking
  - PlayerEvent     : structured events emitted each frame

No pygame, no rendering. Pure logic only.
Scene layer reads .state, .health, .combo_stack and draws accordingly.

Player States
  "idle"    → standing, waiting for input
  "attack"  → successful hit landed  (timed, auto-returns to idle)
  "hurt"    → took damage from miss  (timed, auto-returns to idle)
  "dead"    → health reached zero
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing      import Optional
import math


# CONFIG 

@dataclass(frozen=True)
class PlayerConfig:
    max_health:        int   = 100      # starting health
    damage_on_miss:    int   = 20       # damage taken per miss / auto-miss
    damage_on_boss:    int   = 35       # extra damage from O(n²) miss
    attack_duration:   float = 300.0   # ms player stays in "attack" state
    hurt_duration:     float = 500.0   # ms player stays in "hurt" state
    combo_stack_limit: int   = 20      # max stack depth before it wraps visually
    x:                 float = 80.0    # player screen x (fixed position)
    y:                 float = 200.0   # player screen y (fixed position)


# COMBO STACK (DSA) 

class ComboStack:
    """
    DSA properties demonstrated:
      - push()  : O(1) — add a hit to the top of the stack
      - pop()   : O(1) — remove top element on miss (collapses whole stack)
      - peek()  : O(1) — read current combo without removing
      - clear() : O(n) — wipe on miss / death

    The scene layer can read .items to render a visual stack of blocks
    growing upward as the combo climbs — making the DSA visible in gameplay.
    """

    def __init__(self, limit: int = 20):
        self._stack: list[str] = []   # each entry is the enemy type defeated
        self.limit  = limit
        self.peak   = 0               # highest combo reached this session

    def push(self, enemy_type: str):
        """Record a successful hit. Pushes enemy type onto stack."""
        if len(self._stack) < self.limit:
            self._stack.append(enemy_type)
        else:
            # At limit — rotate (drop bottom, push top) so visual stays bounded
            self._stack.pop(0)
            self._stack.append(enemy_type)
        if len(self._stack) > self.peak:
            self.peak = len(self._stack)

    def pop_all(self):
        """Miss — collapse the entire stack. Returns how many were lost."""
        lost = len(self._stack)
        self._stack.clear()
        return lost

    def peek(self) -> Optional[str]:
        """Top of stack — the last enemy defeated."""
        return self._stack[-1] if self._stack else None

    def clear(self):
        self._stack.clear()

    @property
    def size(self) -> int:
        return len(self._stack)

    @property
    def items(self) -> list[str]:
        """Read-only snapshot for the renderer."""
        return list(self._stack)

    @property
    def is_empty(self) -> bool:
        return len(self._stack) == 0

    def multiplier(self) -> float:
        """
        Score multiplier derived from stack size.
        Stack of 1  → 1.0x
        Stack of 5  → 1.5x
        Stack of 10 → 2.0x
        Stack of 20 → 3.0x (capped)
        """
        return min(1.0 + (self.size * 0.1), 3.0)

    def __repr__(self) -> str:
        return f"ComboStack(size={self.size}, peak={self.peak}, top={self.peek()})"


# PLAYER EVENT 

@dataclass
class PlayerEvent:
    """
    Emitted by Player.update() and Player.react_to_hit().
    Scene layer reads these to trigger sound, screen shake, etc.
    """
    kind:          str            # "STATE_CHANGE" | "DAMAGED" | "DEAD" | "COMBO_LOST"
    new_state:     Optional[str] = None
    damage:        int           = 0
    combo_lost:    int           = 0     # how many stack items were lost
    health_left:   int           = 0


# PLAYER

class Player:
    """
    The main character. Pure logic — no rendering.

    The scene layer reads:
      .state          → which sprite/animation to show
      .health         → for the memory bar HUD
      .combo_stack    → for the visual stack widget
      .x, .y          → where to draw the character
      .wobble         → subtle idle animation offset

    Reacts to HitResult objects from ComplexityEngine via react_to_hit().
    Reacts to auto-misses via take_damage().
    """

    def __init__(self, config: PlayerConfig = PlayerConfig()):
        self.cfg          = config
        self.health       = config.max_health
        self.state        = "idle"
        self.x            = config.x
        self.y            = config.y
        self.combo_stack  = ComboStack(limit=config.combo_stack_limit)

        # Internal timers
        self._state_timer: float = 0.0   # counts down while in attack/hurt
        self._wobble_t:    float = 0.0   # idle animation clock

        # Session stats
        self.total_hits:    int = 0
        self.total_misses:  int = 0
        self.boss_kills:    int = 0

    # Per frame update 

    def update(self, dt_ms: float) -> list[PlayerEvent]:
        """
        Call every frame.
        Handles timed state transitions (attack → idle, hurt → idle).
        Returns list of PlayerEvents (usually empty).
        """
        events: list[PlayerEvent] = []
        self._wobble_t += 0.05

        if self.state in ("attack", "hurt"):
            self._state_timer -= dt_ms
            if self._state_timer <= 0:
                self._set_state("idle")
                events.append(PlayerEvent(
                    kind        = "STATE_CHANGE",
                    new_state   = "idle",
                    health_left = self.health,
                ))

        return events

    # React to game events 

    def react_to_hit(self, hit_result) -> list[PlayerEvent]:
        """
        Call with a HitResult from ComplexityEngine after every player input.
        Returns PlayerEvents for the scene layer.
        """
        events: list[PlayerEvent] = []

        if hit_result.success:
            # ── Successful hit ─────────────────────────────────────────────
            self.combo_stack.push(hit_result.enemy_type)
            self.total_hits += 1
            if hit_result.is_boss_kill:
                self.boss_kills += 1
            self._set_state("attack")
            events.append(PlayerEvent(
                kind        = "STATE_CHANGE",
                new_state   = "attack",
                health_left = self.health,
            ))

        else:
            # Miss you
            lost   = self.combo_stack.pop_all()
            damage = self.cfg.damage_on_miss
            self.total_misses += 1

            if lost > 0:
                events.append(PlayerEvent(
                    kind        = "COMBO_LOST",
                    combo_lost  = lost,
                    health_left = self.health,
                ))

            events.extend(self._apply_damage(damage))

        return events

    def take_damage(self, is_boss: bool = False) -> list[PlayerEvent]:
        """
        Call on auto-miss (enemy walked past without being hit).
        """
        lost   = self.combo_stack.pop_all()
        damage = self.cfg.damage_on_boss if is_boss else self.cfg.damage_on_miss
        events: list[PlayerEvent] = []

        if lost > 0:
            events.append(PlayerEvent(
                kind        = "COMBO_LOST",
                combo_lost  = lost,
                health_left = self.health,
            ))

        events.extend(self._apply_damage(damage))
        return events

    # Accessors

    @property
    def is_alive(self) -> bool:
        return self.health > 0

    @property
    def is_dead(self) -> bool:
        return self.health <= 0

    @property
    def health_pct(self) -> float:
        """Health as 0.0–1.0 for the HUD bar."""
        return max(self.health / self.cfg.max_health, 0.0)

    @property
    def wobble(self) -> float:
        """
        Gentle idle sway for the scene layer to offset draw_y.
        Stops wobbling when hurt or dead — feels more impactful.
        """
        if self.state in ("hurt", "dead"):
            return 0.0
        return math.sin(self._wobble_t) * 2.5

    @property
    def combo(self) -> int:
        """Current combo count — shorthand for combo_stack.size."""
        return self.combo_stack.size

    @property
    def score_multiplier(self) -> float:
        return self.combo_stack.multiplier()

    @property
    def accuracy(self) -> float:
        attempted = self.total_hits + self.total_misses
        if attempted == 0:
            return 0.0
        return self.total_hits / attempted

    def reset(self):
        """Full reset for game-over / restart."""
        self.health        = self.cfg.max_health
        self.state         = "idle"
        self._state_timer  = 0.0
        self._wobble_t     = 0.0
        self.total_hits    = 0
        self.total_misses  = 0
        self.boss_kills    = 0
        self.combo_stack.clear()

    # Internal helpers

    def _set_state(self, new_state: str):
        self.state = new_state
        if new_state == "attack":
            self._state_timer = self.cfg.attack_duration
        elif new_state == "hurt":
            self._state_timer = self.cfg.hurt_duration

    def _apply_damage(self, amount: int) -> list[PlayerEvent]:
        events: list[PlayerEvent] = []
        self.health = max(self.health - amount, 0)
        self._set_state("hurt")

        events.append(PlayerEvent(
            kind        = "DAMAGED",
            new_state   = "hurt",
            damage      = amount,
            health_left = self.health,
        ))

        if self.health <= 0:
            self._set_state("dead")
            events.append(PlayerEvent(
                kind        = "DEAD",
                new_state   = "dead",
                health_left = 0,
            ))

        return events

    def __repr__(self) -> str:
        return (
            f"Player(state={self.state}, hp={self.health}/{self.cfg.max_health}, "
            f"combo={self.combo}, hits={self.total_hits}, misses={self.total_misses})"
        )


# QUICK TEST (wag nyo nalang po pansinin)

if __name__ == "__main__":
    from complexity_engine import ComplexityEngine, COMPLEXITY_MAP

    print("=== ALGO BATO BIT — Player System Test ===\n")

    engine = ComplexityEngine()
    player = Player()

    print(f"Initial state: {player}\n")

    print("--- Combo Stack (DSA) ---")
    print(f"Stack is a: {type(player.combo_stack._stack).__name__}")
    print(f"Empty?  {player.combo_stack.is_empty}")

    hit_types = ["O(1)", "O(log n)", "O(n)", "O(1)", "O(n²)"]
    for etype in hit_types:
        correct_zone = COMPLEXITY_MAP[etype]["zones"][0]
        result = engine.resolve(etype, correct_zone, True)
        events = player.react_to_hit(result)
        print(f"  push({etype}) → stack size={player.combo_stack.size} "
              f"multiplier={player.score_multiplier:.1f}x")

    print(f"\nStack contents (bottom→top): {player.combo_stack.items}")
    print(f"Peek (top): {player.combo_stack.peek()}")
    print(f"Peak combo: {player.combo_stack.peak}")

    print("\n--- Miss collapses stack ---")
    result = engine.resolve("O(1)", 2, True)  
    events = player.react_to_hit(result)
    for e in events:
        print(f"  Event: {e.kind} | combo_lost={e.combo_lost} | hp={e.health_left}")
    print(f"  Stack after miss: {player.combo_stack.items} (should be empty)")

    print("\n--- Auto-miss damage ---")
    events = player.take_damage(is_boss=False)
    for e in events:
        print(f"  Event: {e.kind} | damage={e.damage} | hp={e.health_left}")

    print("\n--- Burn down health to zero ---")
    while player.is_alive:
        events = player.take_damage()
        for e in events:
            if e.kind in ("DAMAGED", "DEAD"):
                print(f"  {e.kind} | hp={e.health_left}")

    print(f"\nFinal: {player}")
    print(f"Accuracy: {player.accuracy:.0%}")
    print(f"Boss kills: {player.boss_kills}")

    print("\n--- Reset ---")
    player.reset()
    print(f"After reset: {player}")