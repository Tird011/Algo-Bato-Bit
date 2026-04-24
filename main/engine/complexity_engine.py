"""

This module owns:
  - COMPLEXITY_MAP       : the central hashmap for all Big O rules
  - ComplexityEngine     : resolves hits, misses, counters
  - EnemyQueue           : manages the enemy queue (spawn, advance, pop)
  - HitResult            : result object returned after every player action
"""

from dataclasses import dataclass, field
from typing import Optional
import random


# COMPLEXITY MAP (ang hashbrown) 
# counters   : list of enemy types this move can defeat
# zones      : which hit zones (0=left, 1=center, 2=right) trigger this move
# weight     : spawn probability weight (higher = appears more often)
# speed_mod  : how fast the enemy walks toward the player (1.0 = baseline)
# tolerance  : hit window strictness (1.0 = full zone, 0.5 = tight center only)
# points     : base score reward for defeating this enemy
# is_boss    : boss enemies have extra rules applied on top

COMPLEXITY_MAP: dict[str, dict] = {
    "O(1)": {
        # Beaten by O(log n) pressing zone 1
        "counters":  ["O(log n)"],
        "zones":     [0],                  # J key
        "weight":    35,
        "speed_mod": 1.5,
        "tolerance": 0.72,
        "points":    100,
        "is_boss":   False,
        "desc":      "Constant time. Blink and it's gone.",
    },
    "O(log n)": {
        # Beaten by O(n) pressing zone 2
        "counters":  ["O(n)"],
        "zones":     [1],                  # K key
        "weight":    30,
        "speed_mod": 1.2,
        "tolerance": 0.72,
        "points":    150,
        "is_boss":   False,
        "desc":      "Logarithmic. Cuts the problem in half every step.",
    },
    "O(n)": {
        # Beaten by O(1) pressing zone 0
        "counters":  ["O(1)"],
        "zones":     [2],                  # L key
        "weight":    25,
        "speed_mod": 1.0,
        "tolerance": 0.72,
        "points":    200,
        "is_boss":   False,
        "desc":      "Linear. Steady, predictable, manageable.",
    },
    "O(n²)": {
        # Boss — beaten by ANY zone but requires tight timing window
        "counters":  ["O(1)", "O(log n)", "O(n)"],
        "zones":     [2],                  # hint zone for HUD (L key preferred)
        "weight":    10,
        "speed_mod": 0.7,
        "tolerance": 0.45,                 # tight boss window
        "points":    400,
        "is_boss":   True,
        "desc":      "Quadratic. Slow but punishing. Any key beats it — if your timing is perfect.",
    },
}

# Flat lists derived from the map — used by spawn logic
ENEMY_TYPES:    list[str] = list(COMPLEXITY_MAP.keys())
SPAWN_WEIGHTS:  list[int] = [COMPLEXITY_MAP[e]["weight"] for e in ENEMY_TYPES]


# ─── HIT RESULT ───────────────────────────────────────────────────────────────

@dataclass
class HitResult:
    """
    Returned by ComplexityEngine.resolve() after every player input.
    The game layer reads this and decides what to render / play.
    """
    success:        bool            # True = enemy defeated
    points:         int             # points awarded (0 on miss)
    streak_bonus:   int             # extra points from streak multiplier
    feedback:       str             # display string e.g. "TAMA!", "MALI!"
    enemy_type:     str             # which enemy was targeted
    pressed_zone:   int             # which zone the player pressed
    correct_zone:   int             # which zone was actually needed
    marker_was_ok:  bool            # was the timing bar in the right position
    is_boss_kill:   bool = False    # special flag for O(n²) defeats


# ─── COMPLEXITY ENGINE ────────────────────────────────────────────────────────

class ComplexityEngine:
    """
    Owns the RPS resolution logic.
    Given a player's pressed zone, the front enemy's type, and whether
    the timing marker was inside a valid window — returns a HitResult.

    Keeps track of streak internally.
    """

    def __init__(self):
        self.streak: int = 0

    def resolve(
        self,
        enemy_type:   str,
        pressed_zone: int,
        marker_ok:    bool,
    ) -> HitResult:
        """
        Core resolution method.

        enemy_type   : key into COMPLEXITY_MAP e.g. "O(n²)"
        pressed_zone : 0, 1, or 2 (J / K / L)
        marker_ok    : True if the timing bar was inside the hit window
                       (checked externally by ExecutionBar)
        """
        data         = COMPLEXITY_MAP[enemy_type]
        correct_zone = data["zones"][0]      # primary zone hint for HUD
        beaten_by    = data["counters"]      # which types beat this enemy

        # Build winning zones from beaten_by.
        # e.g. O(log n) beaten_by ["O(n)","O(n2)"] -> zones {2}
        # O(n2) beaten_by ["O(1)","O(log n)","O(n)"] -> zones {0,1,2}
        winning_zones = {COMPLEXITY_MAP[b]["zones"][0] for b in beaten_by}

        # Win if pressed zone is in winning_zones AND timing was good
        zone_correct = (pressed_zone in winning_zones)
        success      = zone_correct and marker_ok

        if success:
            self.streak += 1
            base_points    = data["points"]
            streak_bonus   = (self.streak - 1) * 50   # bonus starts on 2nd hit
            total_points   = base_points + streak_bonus
            feedback       = self._win_feedback(self.streak, data["is_boss"])
            return HitResult(
                success        = True,
                points         = total_points,
                streak_bonus   = streak_bonus,
                feedback       = feedback,
                enemy_type     = enemy_type,
                pressed_zone   = pressed_zone,
                correct_zone   = correct_zone,
                marker_was_ok  = marker_ok,
                is_boss_kill   = data["is_boss"],
            )

        # ── Loss condition ─────────────────────────────────────────────────────
        else:
            self.streak = 0
            feedback    = self._loss_feedback(
                wrong_zone  = not zone_correct,
                bad_timing  = not marker_ok,
                is_boss     = data["is_boss"],
            )
            return HitResult(
                success        = False,
                points         = 0,
                streak_bonus   = 0,
                feedback       = feedback,
                enemy_type     = enemy_type,
                pressed_zone   = pressed_zone,
                correct_zone   = correct_zone,
                marker_was_ok  = marker_ok,
            )

    def reset_streak(self):
        """Call this on auto-miss (enemy walks past player)."""
        self.streak = 0

    # ── Feedback strings ──────────────────────────────────────────────────────

    def _win_feedback(self, streak: int, is_boss: bool) -> str:
        if is_boss:
            return "BOSS KILL! LODI!"
        if streak >= 10:
            return f"GALING! x{streak} STREAK!"
        if streak >= 5:
            return f"TAMA! x{streak}"
        if streak >= 2:
            return f"TAMA! x{streak}"
        return "TAMA!"

    def _loss_feedback(self, wrong_zone: bool, bad_timing: bool, is_boss: bool) -> str:
        if is_boss:
            return "MEMORY LEAK! BOSS HIT YOU!"
        if wrong_zone and bad_timing:
            return "MALI! Wrong move + bad timing!"
        if wrong_zone:
            return "MALI! Wrong algorithm!"
        if bad_timing:
            return "MALI! Off-beat!"
        return "MALI!"


# ─── ENEMY DATA ───────────────────────────────────────────────────────────────

@dataclass
class Enemy:
    """
    Pure data object. No rendering logic here.
    The game layer reads x, y, complexity and draws whatever it wants.
    """
    complexity:  str
    x:           float
    y:           float
    alive:       bool  = True
    _wobble_t:   float = field(default_factory=lambda: random.uniform(0, 6.28))

    @property
    def data(self) -> dict:
        """Convenience access to this enemy's complexity data."""
        return COMPLEXITY_MAP[self.complexity]

    @property
    def speed(self) -> float:
        return self.data["speed_mod"]

    @property
    def tolerance(self) -> float:
        return self.data["tolerance"]

    @property
    def is_boss(self) -> bool:
        return self.data["is_boss"]

    def update(self, dt_ms: float, base_speed: float = 1.8):
        """Advance enemy toward player. Call every frame."""
        self.x      -= self.speed * base_speed * (dt_ms / 16.67)
        self._wobble_t += 0.08

    @property
    def wobble(self) -> float:
        """Sine-based wobble offset for the game layer to apply to draw_y."""
        import math
        return math.sin(self._wobble_t) * 3.0


# ─── ENEMY QUEUE ──────────────────────────────────────────────────────────────

class EnemyQueue:
    """
    Manages the line of enemies walking toward the player.

    Responsibilities:
      - Spawning enemies on a timer with weighted random selection
      - Maintaining queue spacing so enemies don't overlap
      - Auto-missing if the front enemy walks past the hit line
      - Exposing the front enemy for the engine to resolve against
    """

    SPAWN_INTERVAL_MS: int   = 2800     # base ms between spawns
    SPAWN_VARIANCE:    float = 0.3      # ±30% random variance
    QUEUE_SPACING:     float = 110.0    # px between enemies
    FRONT_TARGET_X:    float = 120.0    # x position where front enemy stops
    AUTO_MISS_X:       float = 40.0     # x position that triggers auto-miss
    ENTRY_X:           float = 1000.0   # enemies spawn from the right

    def __init__(self, engine: ComplexityEngine):
        self.engine:       ComplexityEngine = engine
        self.queue:        list[Enemy]      = []
        self._spawn_timer: float            = 0.0
        self._next_spawn:  float            = float(self.SPAWN_INTERVAL_MS)
        self.memory_leak:  int              = 0    # accumulated damage this session
        self.auto_misses:  int              = 0    # enemies that walked past

    # ── Spawning ──────────────────────────────────────────────────────────────

    def _spawn(self):
        complexity = random.choices(ENEMY_TYPES, weights=SPAWN_WEIGHTS, k=1)[0]
        self.queue.append(Enemy(
            complexity = complexity,
            x          = self.ENTRY_X,
            y          = 80.0,
        ))

    def _next_spawn_interval(self) -> float:
        variance = self.SPAWN_VARIANCE
        low  = self.SPAWN_INTERVAL_MS * (1 - variance)
        high = self.SPAWN_INTERVAL_MS * (1 + variance)
        return random.uniform(low, high)

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt_ms: float) -> Optional[str]:
        """
        Call every frame.
        Returns "AUTO_MISS" if the front enemy walked past — game layer
        should apply memory damage and call engine.reset_streak().
        Returns None otherwise.
        """
        # Spawn timer
        self._spawn_timer += dt_ms
        if self._spawn_timer >= self._next_spawn:
            self._spawn_timer = 0
            self._next_spawn  = self._next_spawn_interval()
            self._spawn()

        # Move all enemies
        for enemy in self.queue:
            enemy.update(dt_ms)

        # Enforce spacing — front enemy stops at FRONT_TARGET_X
        # others maintain QUEUE_SPACING behind the one ahead
        if self.queue:
            front = self.queue[0]
            if front.x < self.FRONT_TARGET_X:
                front.x = self.FRONT_TARGET_X

            for i in range(1, len(self.queue)):
                min_x = self.queue[i - 1].x + self.QUEUE_SPACING
                if self.queue[i].x < min_x:
                    self.queue[i].x = min_x

        # Auto-miss check — front enemy walked past the hit line
        if self.queue and self.queue[0].x < self.AUTO_MISS_X:
            self.queue.pop(0)
            self.auto_misses += 1
            self.engine.reset_streak()
            return "AUTO_MISS"

        return None

    # ── Player action ─────────────────────────────────────────────────────────

    def handle_input(self, pressed_zone: int, marker_ok: bool) -> Optional[HitResult]:
        """
        Called when the player presses J / K / L.
        Returns HitResult if there's a front enemy, None if queue is empty.
        """
        if not self.queue:
            return None

        front  = self.queue[0]
        result = self.engine.resolve(front.complexity, pressed_zone, marker_ok)

        if result.success:
            front.alive = False
            self.queue.pop(0)

        return result

    # ── Accessors ─────────────────────────────────────────────────────────────

    @property
    def front(self) -> Optional[Enemy]:
        """The enemy the player is currently facing."""
        return self.queue[0] if self.queue else None

    @property
    def count(self) -> int:
        return len(self.queue)

    def clear(self):
        self.queue.clear()
        self.auto_misses  = 0
        self.memory_leak  = 0


# ─── QUICK TEST (run this file directly to verify logic) ──────────────────────

if __name__ == "__main__":
    print("=== ALGO BATO BIT — Complexity Engine Test ===\n")

    engine = ComplexityEngine()
    q      = EnemyQueue(engine)

    # Manually inject enemies for testing
    test_cases = [
        ("O(1)",    0, True,  "Should WIN  — correct zone + good timing"),
        ("O(1)",    1, True,  "Should LOSE — wrong zone"),
        ("O(log n)",1, True,  "Should WIN  — correct zone + good timing"),
        ("O(log n)",2, True,  "Should WIN  — zone 2 also counters O(n²) not O(log n), LOSE"),
        ("O(n²)",   2, True,  "Should WIN  — O(n) counters O(n²), correct zone"),
        ("O(n²)",   2, False, "Should LOSE — correct zone but bad timing"),
        ("O(n²)",   0, True,  "Should WIN  — O(1) counters O(n²), but zone 0 != zone 2, LOSE"),
    ]

    for enemy_type, zone, timing, description in test_cases:
        result = engine.resolve(enemy_type, zone, timing)
        status = " WIN " if result.success else " LOSE"
        print(f"{status} | {enemy_type} vs Zone {zone} | timing={timing}")
        print(f"       {description}")
        print(f"       feedback='{result.feedback}' points={result.points} streak={engine.streak}\n")

    print("=== Hashmap dump ===\n")
    for name, data in COMPLEXITY_MAP.items():
        print(f"{name:12} | counters={data['counters']} | zones={data['zones']} "
              f"| boss={data['is_boss']} | pts={data['points']}")