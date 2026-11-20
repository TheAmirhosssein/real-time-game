"""In-memory movement buffer sampled ~15 Hz, flushed in one ORM batch insert."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from core_duel.core.entities import InputState, PlayerCore

if TYPE_CHECKING:
    from core_duel.services.database import DatabaseManager

SAMPLE_EVERY_TICKS = 4  # 60 FPS → 15 Hz


class TelemetryBuffer:
    def __init__(self, match_id: str, db: "DatabaseManager") -> None:
        self.match_id = match_id
        self.db = db
        self._rows: list[tuple] = []
        self.shots_p1 = 0
        self.shots_p2 = 0
        self.hits_p1 = 0
        self.hits_p2 = 0
        self.dashes_p1 = 0
        self.dashes_p2 = 0
        self._started = time.time()

    def record_tick(
        self,
        tick: int,
        p1: PlayerCore,
        p2: PlayerCore,
        p1_input: InputState,
        p2_input: InputState,
        events: list[str],
        p1_id: str,
    ) -> None:
        if p1_input.fire:
            self.shots_p1 += 1
        if p2_input.fire:
            self.shots_p2 += 1
        if p1_input.dash:
            self.dashes_p1 += 1
        if p2_input.dash:
            self.dashes_p2 += 1
        if "hit" in events:
            # attribute loosely: whoever is on cooldown just after a shot is attacker
            if p1.fire_cd > 0:
                self.hits_p1 += 1
            elif p2.fire_cd > 0:
                self.hits_p2 += 1

        if tick % SAMPLE_EVERY_TICKS != 0:
            return
        now_ms = int(time.time() * 1000)
        self._rows.append(self._row(p1, tick, now_ms, p1_input))
        self._rows.append(self._row(p2, tick, now_ms, p2_input))
        if len(self._rows) >= 120:
            self.flush()

    def _row(self, player: PlayerCore, tick: int, now_ms: int, inp: InputState) -> tuple:
        flags = json.dumps({"dash": bool(inp.dash), "fire": bool(inp.fire)})
        return (
            self.match_id,
            player.user_id,
            tick,
            now_ms,
            player.x,
            player.y,
            player.vx,
            player.vy,
            player.angle,
            flags,
        )

    def flush(self) -> None:
        rows, self._rows = self._rows, []
        self.db.insert_movement_logs(rows)

    def summary(self, local_is_p1: bool) -> dict:
        shots = self.shots_p1 if local_is_p1 else self.shots_p2
        hits = self.hits_p1 if local_is_p1 else self.hits_p2
        dashes = self.dashes_p1 if local_is_p1 else self.dashes_p2
        acc = (hits / shots * 100.0) if shots else 0.0
        return {
            "shots": shots,
            "hits": hits,
            "accuracy": acc,
            "dashes": dashes,
            "duration": time.time() - self._started,
        }
