"""
Owns the bouncing marker and hit zone logic.
No rendering here — scene layer reads state and draws.

Zones
─────
  0 (LEFT)   → J key → counters O(1) enemies
  1 (CENTER) → K key → counters O(log n) enemies
  2 (RIGHT)  → L key → counters O(n) / O(n²) enemies
"""

from __future__ import annotations
from dataclasses import dataclass



@dataclass(frozen=True)
class BarConfig:
    x:             float = 60.0    # left edge of bar in screen px
    width:         float = 840.0   # total bar width
    speed_base:    float = 3.0     # marker px/frame at 60fps
    speed_max:     float = 6.5     # cap so it never becomes unplayable
    speed_step:    float = 0.15    # speed added per streak hit
    flash_ms:      float = 220.0   # how long a zone flash lasts



@dataclass
class BarEvent:
    kind:     str   # "FLASH" | "BOUNCE"
    zone:     int   = 0
    success:  bool  = False



class ExecutionBar:
    """
    Bouncing marker across three hit zones.

    Scene layer reads:
      .marker_x          → where to draw the marker cursor
      .zone_x(i)         → left edge of zone i
      .zone_width        → width of each zone (all equal)
      .flash_state(i)    → (color_key, intensity 0–1) or None
      .marker_zone       → which zone (0/1/2) the marker is currently in
    """

    ZONE_KEYS = ["O(1)", "O(log n)", "O(n)"]   # zone index → complexity label

    def __init__(self, config: BarConfig = BarConfig()):
        self.cfg        = config
        self.marker_x   = config.x
        self._direction = 1        # +1 right, -1 left
        self._speed     = config.speed_base
        self._flashes:  dict[int, float] = {}   # zone → remaining ms


    def update(self, dt_ms: float) -> list[BarEvent]:
        events: list[BarEvent] = []

        # Move marker
        self.marker_x += self._direction * self._speed * (dt_ms / 16.67)

        right_edge = self.cfg.x + self.cfg.width
        if self.marker_x >= right_edge:
            self.marker_x  = right_edge
            self._direction = -1
            events.append(BarEvent(kind="BOUNCE", zone=2))
        elif self.marker_x <= self.cfg.x:
            self.marker_x  = self.cfg.x
            self._direction = 1
            events.append(BarEvent(kind="BOUNCE", zone=0))

        # Decay flashes
        for zone in list(self._flashes):
            self._flashes[zone] -= dt_ms
            if self._flashes[zone] <= 0:
                del self._flashes[zone]

        return events


    @property
    def zone_width(self) -> float:
        return self.cfg.width / 3

    def zone_x(self, zone_idx: int) -> float:
        """Left edge x of zone 0, 1, or 2."""
        return self.cfg.x + zone_idx * self.zone_width

    @property
    def marker_zone(self) -> int:
        """Which zone (0/1/2) the marker is currently inside."""
        rel = self.marker_x - self.cfg.x
        return min(int(rel // self.zone_width), 2)


    def marker_in_window(self, zone_idx: int, tolerance: float) -> bool:
        """
        True if marker is comfortably inside zone_idx.

        tolerance comes from COMPLEXITY_MAP[enemy]["tolerance"]:
          0.72 = standard window (72% of zone width)
          0.45 = boss window (45% — much tighter)

        Called by game.py before passing marker_ok to queue.handle_input().
        """
        left   = self.zone_x(zone_idx)
        right  = left + self.zone_width
        margin = self.zone_width * (1 - tolerance) / 2
        return left + margin <= self.marker_x <= right - margin


    def trigger_flash(self, zone_idx: int, success: bool):
        """
        Call after a hit attempt.
        Scene layer reads flash_state() to color the zone.
        """
        self._flashes[zone_idx] = self.cfg.flash_ms

    def flash_intensity(self, zone_idx: int) -> float:
        """
        0.0 = no flash, 1.0 = full flash.
        Scene layer uses this to lerp zone color toward hit/miss color.
        """
        if zone_idx not in self._flashes:
            return 0.0
        return self._flashes[zone_idx] / self.cfg.flash_ms


    def on_hit(self, streak: int):
        """Speed up slightly on each streak hit. Capped at speed_max."""
        self._speed = min(
            self.cfg.speed_base + streak * self.cfg.speed_step,
            self.cfg.speed_max,
        )

    def on_miss(self):
        """Reset speed on miss."""
        self._speed = self.cfg.speed_base

    def reset(self):
        self.marker_x   = self.cfg.x
        self._direction = 1
        self._speed     = self.cfg.speed_base
        self._flashes.clear()

    def __repr__(self) -> str:
        return (
            f"ExecutionBar(marker={self.marker_x:.1f}, "
            f"zone={self.marker_zone}, speed={self._speed:.2f})"
        )



if __name__ == "__main__":
    print("=== ALGO BATO BIT — Execution Bar Test ===\n")

    bar = ExecutionBar()

    # Simulate 120 frames and track zone visits
    zone_visits = {0: 0, 1: 0, 2: 0}
    bounces     = 0

    for frame in range(120):
        events = bar.update(dt_ms=16.67)
        zone_visits[bar.marker_zone] += 1
        for e in events:
            if e.kind == "BOUNCE":
                bounces += 1

    print(f"After 120 frames (~2s):")
    print(f"  Zone visits → L:{zone_visits[0]} C:{zone_visits[1]} R:{zone_visits[2]}")
    print(f"  Bounces: {bounces}")
    print(f"  Final marker x: {bar.marker_x:.1f}")
    print(f"  Current zone:   {bar.marker_zone}\n")

    # Test hit windows
    print("Hit window tests (standard tolerance=0.72):")
    bar.marker_x = bar.zone_x(0) + bar.zone_width * 0.5   # dead center zone 0
    print(f"  Center of zone 0 → in_window(0, 0.72): {bar.marker_in_window(0, 0.72)}")
    bar.marker_x = bar.zone_x(0) + bar.zone_width * 0.01  # near edge zone 0
    print(f"  Edge of zone 0   → in_window(0, 0.72): {bar.marker_in_window(0, 0.72)}")

    print("\nBoss window tests (tight tolerance=0.45):")
    bar.marker_x = bar.zone_x(2) + bar.zone_width * 0.5   # dead center zone 2
    print(f"  Center of zone 2 → in_window(2, 0.45): {bar.marker_in_window(2, 0.45)}")
    bar.marker_x = bar.zone_x(2) + bar.zone_width * 0.35  # slightly off center
    print(f"  Off-center zone 2→ in_window(2, 0.45): {bar.marker_in_window(2, 0.45)}")

    # Test speed scaling
    print("\nSpeed scaling:")
    for streak in [0, 3, 5, 10, 20]:
        bar.on_hit(streak)
        print(f"  streak={streak:2d} → speed={bar._speed:.2f}")