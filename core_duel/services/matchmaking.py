"""Score-range queue, expanding brackets, and ELO (K=32)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from core_duel.services.database import DatabaseManager

ARENA_PRESETS = (
    "Standard Containment",
    "Twin Pillars",
    "Overclocked",
)

ELO_K = 32


@dataclass
class QueueStatus:
    searching: bool
    elapsed: float
    bracket_low: int
    bracket_high: int
    range_limit: int
    matched: bool
    match_id: Optional[str]
    opponent_id: Optional[str]
    is_host: bool
    arena_preset: str
    room_endpoint: Optional[str]


def elo_deltas(winner_score: int, loser_score: int, k: int = ELO_K) -> tuple[int, int]:
    expected = 1.0 / (1.0 + 10 ** ((loser_score - winner_score) / 400.0))
    win_delta = int(round(k * (1.0 - expected)))
    lose_delta = -win_delta
    return win_delta, lose_delta


def search_range_for_elapsed(elapsed: float) -> int:
    if elapsed < 5.0:
        return 100
    if elapsed < 15.0:
        return 250
    return 500


class MatchmakingService:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self._joined_at: dict[str, float] = {}

    def enqueue(self, user: dict[str, Any], arena_preset: str) -> None:
        if arena_preset not in ARENA_PRESETS:
            arena_preset = ARENA_PRESETS[0]
        self._joined_at[user["user_id"]] = time.monotonic()
        self.db.execute(
            """
            INSERT INTO matchmaking_queue (user_id, score, arena_preset, status, matched_room_id, joined_at)
            VALUES (?, ?, ?, 'SEARCHING', NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                score = excluded.score,
                arena_preset = excluded.arena_preset,
                status = 'SEARCHING',
                matched_room_id = NULL,
                joined_at = CURRENT_TIMESTAMP
            """,
            (user["user_id"], user["score"], arena_preset),
        )

    def cancel(self, user_id: str) -> None:
        self._joined_at.pop(user_id, None)
        self.db.execute("DELETE FROM matchmaking_queue WHERE user_id = ?", (user_id,))

    def poll(self, user_id: str) -> QueueStatus:
        row = self.db.query_one(
            "SELECT * FROM matchmaking_queue WHERE user_id = ?", (user_id,)
        )
        if row is None:
            user = self.db.get_user_by_id(user_id)
            score = user["score"] if user else 1000
            return QueueStatus(
                searching=False,
                elapsed=0.0,
                bracket_low=score,
                bracket_high=score,
                range_limit=100,
                matched=False,
                match_id=None,
                opponent_id=None,
                is_host=False,
                arena_preset=ARENA_PRESETS[0],
                room_endpoint=None,
            )

        elapsed = self._elapsed_seconds(row["user_id"], row["joined_at"])
        rng = search_range_for_elapsed(elapsed)
        score = int(row["score"])

        if row["status"] == "MATCHED" and row["matched_room_id"]:
            return self._status_from_matched_row(row, elapsed, rng, score)

        self._try_pair(user_id, score, rng, row["arena_preset"])
        row = self.db.query_one(
            "SELECT * FROM matchmaking_queue WHERE user_id = ?", (user_id,)
        )
        if row and row["status"] == "MATCHED" and row["matched_room_id"]:
            return self._status_from_matched_row(row, elapsed, rng, score)

        return QueueStatus(
            searching=True,
            elapsed=elapsed,
            bracket_low=max(0, score - rng),
            bracket_high=score + rng,
            range_limit=rng,
            matched=False,
            match_id=None,
            opponent_id=None,
            is_host=False,
            arena_preset=row["arena_preset"] if row else ARENA_PRESETS[0],
            room_endpoint=None,
        )

    def publish_endpoint(self, user_id: str, endpoint: str) -> None:
        row = self.db.query_one(
            "SELECT matched_room_id FROM matchmaking_queue WHERE user_id = ?", (user_id,)
        )
        if not row or not row["matched_room_id"]:
            return
        match_id = str(row["matched_room_id"]).split("@", 1)[0]
        room = f"{match_id}@{endpoint}"
        self.db.execute(
            "UPDATE matchmaking_queue SET matched_room_id = ? WHERE matched_room_id LIKE ?",
            (room, f"{match_id}%"),
        )

    def _try_pair(self, user_id: str, score: int, rng: int, arena_preset: str) -> None:
        conn = self.db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            me = conn.execute(
                "SELECT * FROM matchmaking_queue WHERE user_id = ? AND status = 'SEARCHING'",
                (user_id,),
            ).fetchone()
            if me is None:
                conn.rollback()
                return
            opponent = conn.execute(
                """
                SELECT * FROM matchmaking_queue
                WHERE user_id != ?
                  AND status = 'SEARCHING'
                  AND ABS(score - ?) <= ?
                ORDER BY joined_at ASC
                LIMIT 1
                """,
                (user_id, score, rng),
            ).fetchone()
            if opponent is None and rng >= 500:
                opponent = conn.execute(
                    """
                    SELECT * FROM matchmaking_queue
                    WHERE user_id != ? AND status = 'SEARCHING'
                    ORDER BY joined_at ASC
                    LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
            if opponent is None:
                conn.rollback()
                return
            match_id = str(uuid.uuid4())
            host_id = user_id if me["joined_at"] <= opponent["joined_at"] else opponent["user_id"]
            guest_id = opponent["user_id"] if host_id == user_id else user_id
            preset = me["arena_preset"] or arena_preset
            conn.execute(
                "UPDATE matchmaking_queue SET status = 'MATCHED', matched_room_id = ? WHERE user_id IN (?, ?)",
                (match_id, host_id, guest_id),
            )
            p1 = self.db.get_user_by_id(host_id)
            p2 = self.db.get_user_by_id(guest_id)
            conn.execute(
                """
                INSERT OR IGNORE INTO matches (
                    match_id, player1_id, player2_id, p1_score_before, p2_score_before, arena_preset
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    host_id,
                    guest_id,
                    p1["score"] if p1 else score,
                    p2["score"] if p2 else opponent["score"],
                    preset,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _status_from_matched_row(self, row, elapsed: float, rng: int, score: int) -> QueueStatus:
        raw = str(row["matched_room_id"])
        match_id, _, endpoint = raw.partition("@")
        match = self.db.query_one("SELECT * FROM matches WHERE match_id = ?", (match_id,))
        opponent_id = None
        is_host = False
        if match:
            if match["player1_id"] == row["user_id"]:
                opponent_id = match["player2_id"]
                is_host = True
            else:
                opponent_id = match["player1_id"]
                is_host = False
        return QueueStatus(
            searching=False,
            elapsed=elapsed,
            bracket_low=max(0, score - rng),
            bracket_high=score + rng,
            range_limit=rng,
            matched=True,
            match_id=match_id,
            opponent_id=opponent_id,
            is_host=is_host,
            arena_preset=row["arena_preset"],
            room_endpoint=endpoint or None,
        )

    def _elapsed_seconds(self, user_id: str, joined_at: str) -> float:
        started = self._joined_at.get(user_id)
        if started is not None:
            return max(0.0, time.monotonic() - started)
        try:
            parts = time.strptime(str(joined_at).split(".")[0], "%Y-%m-%d %H:%M:%S")
            return max(0.0, time.time() - time.mktime(parts))
        except Exception:
            return 0.0

    def create_local_match(
        self, user: dict[str, Any], rival: dict[str, Any], arena_preset: str
    ) -> str:
        match_id = str(uuid.uuid4())
        self.db.insert_match(
            match_id=match_id,
            player1_id=user["user_id"],
            player2_id=rival["user_id"],
            p1_score_before=user["score"],
            p2_score_before=rival["score"],
            arena_preset=arena_preset,
        )
        return match_id
