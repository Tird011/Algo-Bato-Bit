"""
Pure data object.
Scene layer reads HUD fields and draws whatever it wants.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class HUD:
    score:           int   = 0
    high_score:      int   = 0
    memory:          int   = 100     # player health rebranded as "memory"
    max_memory:      int   = 100
    streak:          int   = 0
    best_streak:     int   = 0
    multiplier:      float = 1.0
    feedback:        str   = ""
    feedback_timer:  float = 0.0     # ms remaining to show feedback
    accuracy:        float = 0.0

    # DSA labels shown on screen — teaches while playing
    dsa_label:       str   = "Queue: 0 enemies"
    stack_label:     str   = "Stack: empty"

    def update(self, dt_ms: float):
        """Tick down feedback timer each frame."""
        if self.feedback_timer > 0:
            self.feedback_timer -= dt_ms
            if self.feedback_timer <= 0:
                self.feedback       = ""
                self.feedback_timer = 0.0

    def set_feedback(self, text: str, duration_ms: float = 700.0):
        self.feedback       = text
        self.feedback_timer = duration_ms

    def sync_player(self, player):
        """Pull live data from Player object."""
        self.memory      = player.health
        self.streak      = player.combo
        self.multiplier  = player.score_multiplier
        self.accuracy    = player.accuracy
        if player.combo > self.best_streak:
            self.best_streak = player.combo
        self.stack_label = (
            f"Stack: {player.combo_stack.size} "
            f"[{', '.join(player.combo_stack.items[-3:])}]"
            if not player.combo_stack.is_empty
            else "Stack: empty"
        )

    def sync_queue(self, queue):
        """Pull live data from EnemyQueue object."""
        self.dsa_label = f"Queue: {queue.count} enemies"

    def add_score(self, points: int):
        self.score += points
        if self.score > self.high_score:
            self.high_score = self.score

    def reset(self):
        self.score          = 0
        self.memory         = self.max_memory
        self.streak         = 0
        self.multiplier     = 1.0
        self.feedback       = ""
        self.feedback_timer = 0.0
        self.accuracy       = 0.0
        self.dsa_label      = "Queue: 0 enemies"
        self.stack_label    = "Stack: empty"