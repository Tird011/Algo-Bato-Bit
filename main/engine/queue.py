"""

Owns everything about the enemy line:
  - EnemyQueue     : spawn, advance, space, auto-miss
  - Enemy          : pure data object, no rendering
  - QueueEvent     : structured event returned each frame

Talks to ComplexityEngine for hit resolution.
The game/scene layer reads QueueEvents and decides what to render.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing      import Optional, TYPE_CHECKING
import random
import math

if TYPE_CHECKING:
    from complexity_engine import ComplexityEngine, HitResult

from complexity_engine import COMPLEXITY_MAP, ENEMY_TYPES, SPAWN_WEIGHTS


# ─── QUEUE CONFIG ─────────────────────────────────────────────────────────────
# All tunable values in one place — change here, affects everything.

@dataclass(frozen=True)
class QueueConfig:
    spawn_interval_ms: float = 2800.0   # base ms between enemy spawns
    spawn_variance:    float = 0.30     # ±% random jitter on spawn interval
    queue_spacing:     float = 110.0    # minimum px between enemies
    front_target_x:    float = 120.0    # x where front enemy stops and waits
    auto_miss_x:       float = 40.0     # x where front enemy triggers auto-miss
    entry_x:           float = 1000.0   # x where new enemies are born (off-screen right)
    base_speed:        float = 1.8      # base movement speed in px/frame at 60fps
    speed_scale_max:   float = 2.5      # cap on how fast enemies can get


# ─── QUEUE EVENTS ─────────────────────────────────────────────────────────────
# The queue never talks to the renderer directly.
# Instead it emits QueueEvents each frame — the scene layer reads and reacts.

@dataclass
class QueueEvent:
    kind:        str              # "AUTO_MISS" | "HIT_RESULT" | "SPAWNED" | "EMPTY"
    hit_result:  Optional[object] = None   # HitResult if kind == "HIT_RESULT"
    enemy_type:  Optional[str]   = None   # which enemy triggered the event
    queue_count: int             = 0      # how many enemies remain after event
    is_boss:     bool            = False  # True if auto-missed enemy was O(n²)


# ─── ENEMY ────────────────────────────────────────────────────────────────────

@dataclass
class Enemy:
    """
    Pure data. No pygame surfaces, no draw calls.
    The scene layer reads .x, .y, .complexity, .state and renders accordingly.

    States
    ------
    "walk"    : enemy is moving toward the player (default)
    "dying"   : enemy was hit — scene layer plays death animation then removes
    "waiting" : enemy reached FRONT_TARGET_X and is holding position
    """
    complexity: str
    x:          float
    y:          float
    state:      str   = "walk"
    alive:      bool  = True

    # Internal animation clock — exposed as .wobble for the scene layer
    _t: float = field(default_factory=lambda: random.uniform(0.0, math.tau))

    # ── Derived from COMPLEXITY_MAP ────────────────────────────────────────

    @property
    def data(self) -> dict:
        return COMPLEXITY_MAP[self.complexity]

    @property
    def speed_mod(self) -> float:
        return self.data["speed_mod"]

    @property
    def tolerance(self) -> float:
        return self.data["tolerance"]

    @property
    def is_boss(self) -> bool:
        return self.data["is_boss"]

    @property
    def points(self) -> int:
        return self.data["points"]

    @property
    def required_zone(self) -> int:
        return self.data["zones"][0]

    @property
    def countered_by(self) -> list[str]:
        return self.data["counters"]

    # ── Per-frame update ───────────────────────────────────────────────────

    def update(self, dt_ms: float, base_speed: float):
        """Move left. Only advances if state is 'walk'."""
        if self.state == "walk":
            self.x -= self.speed_mod * base_speed * (dt_ms / 16.67)
        self._t += 0.08

    @property
    def wobble(self) -> float:
        """
        Sine-based vertical offset for the scene layer to apply when drawing.
        Gives a hand-drawn jitter feel without any art logic here.
        """
        return math.sin(self._t) * 3.0

    def __repr__(self) -> str:
        return f"Enemy({self.complexity}, x={self.x:.1f}, state={self.state})"


# ─── ENEMY QUEUE ──────────────────────────────────────────────────────────────

class EnemyQueue:
    """
    Manages the full enemy line from spawn to removal.

    Usage
    -----
        engine = ComplexityEngine()
        queue  = EnemyQueue(engine)

        # each frame:
        events = queue.update(dt_ms)
        for event in events:
            if event.kind == "AUTO_MISS":
                player.take_damage()

        # on keypress:
        events = queue.handle_input(pressed_zone=0, marker_ok=True)
        for event in events:
            if event.kind == "HIT_RESULT" and event.hit_result.success:
                score += event.hit_result.points
    """

    def __init__(
        self,
        engine: "ComplexityEngine",
        config: QueueConfig = QueueConfig(),
    ):
        self.engine:  "ComplexityEngine" = engine
        self.cfg:     QueueConfig        = config
        self._queue:  list[Enemy]        = []
        self._timer:  float              = 0.0
        self._next:   float              = config.spawn_interval_ms

        # Stats — readable by HUD or game-over screen
        self.total_spawned:  int = 0
        self.total_defeated: int = 0
        self.total_missed:   int = 0

    # ── Public interface ───────────────────────────────────────────────────────

    def update(self, dt_ms: float) -> list[QueueEvent]:
        """
        Advance the queue by one frame.
        Returns a list of QueueEvents (usually 0–1 items, occasionally more).
        """
        events: list[QueueEvent] = []

        # 1. Spawn timer
        self._timer += dt_ms
        if self._timer >= self._next:
            self._timer = 0.0
            self._next  = self._spawn_interval()
            self._spawn()
            events.append(QueueEvent(
                kind        = "SPAWNED",
                enemy_type  = self._queue[-1].complexity if self._queue else None,
                queue_count = len(self._queue),
            ))

        # 2. Move all enemies
        for enemy in self._queue:
            enemy.update(dt_ms, self.cfg.base_speed)

        # 3. Enforce spacing
        self._enforce_spacing()

        # 4. Auto-miss check
        if self._queue and self._queue[0].x < self.cfg.auto_miss_x:
            missed = self._queue.pop(0)
            self.total_missed += 1
            self.engine.reset_streak()
            events.append(QueueEvent(
                kind        = "AUTO_MISS",
                enemy_type  = missed.complexity,
                is_boss     = missed.is_boss,      # player.take_damage() needs this
                queue_count = len(self._queue),
            ))

        # 5. Empty queue notice (useful for pacing / difficulty checks)
        if not self._queue:
            events.append(QueueEvent(kind="EMPTY", queue_count=0))

        return events

    def handle_input(
        self,
        pressed_zone: int,
        marker_ok:    bool,
    ) -> list[QueueEvent]:
        """
        Call when the player presses J / K / L.
        Returns HIT_RESULT event — always, even on miss (success=False).
        Returns empty list if no enemies are queued.
        """
        if not self._queue:
            return []

        front  = self._queue[0]
        result = self.engine.resolve(front.complexity, pressed_zone, marker_ok)

        if result.success:
            front.state = "dying"
            front.alive = False
            self._queue.pop(0)
            self.total_defeated += 1

        return [QueueEvent(
            kind        = "HIT_RESULT",
            hit_result  = result,
            enemy_type  = front.complexity,
            queue_count = len(self._queue),
        )]

    def scale_difficulty(self, score: int):
        """
        Call periodically to increase pressure as score grows.
        Increases base speed and tightens spawn interval.
        Capped to avoid making the game unplayable.
        """
        scale = min(score / 5000, 1.0)   # reaches full scale at 5000 pts
        self.cfg = QueueConfig(
            spawn_interval_ms = max(1200.0, self.cfg.spawn_interval_ms - scale * 800),
            base_speed        = min(
                self.cfg.speed_scale_max,
                1.8 + scale * (self.cfg.speed_scale_max - 1.8)
            ),
            # everything else unchanged
            spawn_variance  = self.cfg.spawn_variance,
            queue_spacing   = self.cfg.queue_spacing,
            front_target_x  = self.cfg.front_target_x,
            auto_miss_x     = self.cfg.auto_miss_x,
            entry_x         = self.cfg.entry_x,
            speed_scale_max = self.cfg.speed_scale_max,
        )

    def reset(self):
        """Full reset for game-over / restart."""
        self._queue.clear()
        self._timer          = 0.0
        self._next           = self.cfg.spawn_interval_ms
        self.total_spawned   = 0
        self.total_defeated  = 0
        self.total_missed    = 0
        self.engine.reset_streak()

    # ── Accessors ─────────────────────────────────────────────────────────────

    @property
    def front(self) -> Optional[Enemy]:
        """The enemy currently facing the player. None if queue is empty."""
        return self._queue[0] if self._queue else None

    @property
    def all_enemies(self) -> list[Enemy]:
        """Read-only view of the full queue for rendering."""
        return list(self._queue)

    @property
    def count(self) -> int:
        return len(self._queue)

    @property
    def accuracy(self) -> float:
        """Hit accuracy as a 0.0–1.0 float. Returns 0 if nothing attempted."""
        attempted = self.total_defeated + self.total_missed
        if attempted == 0:
            return 0.0
        return self.total_defeated / attempted

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _spawn(self):
        complexity = random.choices(ENEMY_TYPES, weights=SPAWN_WEIGHTS, k=1)[0]
        self._queue.append(Enemy(
            complexity = complexity,
            x          = self.cfg.entry_x,
            y          = 80.0,
        ))
        self.total_spawned += 1

    def _spawn_interval(self) -> float:
        v    = self.cfg.spawn_variance
        base = self.cfg.spawn_interval_ms
        return random.uniform(base * (1 - v), base * (1 + v))

    def _enforce_spacing(self):
        """
        Prevents enemies from overlapping.
        Front enemy locks at FRONT_TARGET_X once it arrives.
        Each subsequent enemy maintains QUEUE_SPACING behind the one ahead.
        """
        if not self._queue:
            return

        front = self._queue[0]
        if front.x <= self.cfg.front_target_x:
            front.x    = self.cfg.front_target_x
            front.state = "waiting"

        for i in range(1, len(self._queue)):
            min_x = self._queue[i - 1].x + self.cfg.queue_spacing
            if self._queue[i].x < min_x:
                self._queue[i].x = min_x


# ─── QUICK TEST ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from complexity_engine import ComplexityEngine

    print("=== ALGO BATO BIT — Queue System Test ===\n")

    engine = ComplexityEngine()
    queue  = EnemyQueue(engine)

    # Force spawn 3 enemies manually
    queue._spawn()
    queue._spawn()
    queue._spawn()

    print(f"Queue count: {queue.count}")
    print(f"Front enemy: {queue.front}")
    print(f"All enemies: {queue.all_enemies}\n")

    # Simulate a correct hit on front enemy
    front = queue.front
    if front:
        zone = front.required_zone
        print(f"Front is {front.complexity} — hitting zone {zone} with good timing...")
        events = queue.handle_input(pressed_zone=zone, marker_ok=True)
        for e in events:
            if e.kind == "HIT_RESULT":
                r = e.hit_result
                print(f"  Result: {'WIN' if r.success else 'LOSE'}")
                print(f"  Feedback: {r.feedback}")
                print(f"  Points: {r.points}")
                print(f"  Queue remaining: {e.queue_count}\n")

    # Simulate a miss
    front = queue.front
    if front:
        wrong_zone = (front.required_zone + 1) % 3
        print(f"Front is {front.complexity} — hitting WRONG zone {wrong_zone}...")
        events = queue.handle_input(pressed_zone=wrong_zone, marker_ok=True)
        for e in events:
            if e.kind == "HIT_RESULT":
                r = e.hit_result
                print(f"  Result: {'WIN' if r.success else 'LOSE'}")
                print(f"  Feedback: {r.feedback}")
                print(f"  Points: {r.points}\n")

    # Simulate frame updates
    print("Simulating 180 frames (~3 seconds)...")
    for _ in range(180):
        events = queue.update(dt_ms=16.67)
        for e in events:
            if e.kind == "AUTO_MISS":
                print(f"  AUTO_MISS — {e.enemy_type} walked past!")
            elif e.kind == "SPAWNED":
                print(f"  SPAWNED   — {e.enemy_type} | queue={e.queue_count}")

    print(f"\nFinal stats:")
    print(f"  Spawned:  {queue.total_spawned}")
    print(f"  Defeated: {queue.total_defeated}")
    print(f"  Missed:   {queue.total_missed}")
    print(f"  Accuracy: {queue.accuracy:.0%}")