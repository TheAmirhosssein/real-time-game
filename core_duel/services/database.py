"""SQLite schema, CRUD, and batched movement-log writes (WAL)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    is_guest INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 1000,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS matchmaking_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    score INTEGER NOT NULL,
    arena_preset TEXT DEFAULT 'Standard Containment',
    status TEXT DEFAULT 'SEARCHING',
    matched_room_id TEXT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    player1_id TEXT NOT NULL,
    player2_id TEXT NOT NULL,
    winner_id TEXT,
    p1_score_before INTEGER,
    p2_score_before INTEGER,
    p1_score_delta INTEGER,
    p2_score_delta INTEGER,
    duration_seconds REAL,
    arena_preset TEXT,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player1_id) REFERENCES users(user_id),
    FOREIGN KEY (player2_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS movement_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    pos_x REAL NOT NULL,
    pos_y REAL NOT NULL,
    vel_x REAL NOT NULL,
    vel_y REAL NOT NULL,
    angle REAL NOT NULL,
    action_flags TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(match_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
"""


class DatabaseManager:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        root = Path(__file__).resolve().parents[1]
        data_dir = root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else data_dir / "core_duel.db"
        self._local = threading.local()
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=4000")
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        conn = self.connect()
        conn.executescript(SCHEMA)
        conn.commit()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        conn = self.connect()
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        cur = self.connect().execute(sql, tuple(params))
        return cur.fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        cur = self.connect().execute(sql, tuple(params))
        return cur.fetchone()

    def user_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "is_guest": bool(row["is_guest"]),
            "score": int(row["score"]),
            "wins": int(row["wins"]),
            "losses": int(row["losses"]),
            "email": row["email"],
        }

    def get_user_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        row = self.query_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self.user_to_dict(row) if row else None

    def get_user_by_username(self, username: str) -> Optional[sqlite3.Row]:
        return self.query_one(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        )

    def insert_user(
        self,
        user_id: str,
        username: str,
        password_hash: Optional[str],
        is_guest: bool,
        email: Optional[str] = None,
        score: int = 1000,
    ) -> dict[str, Any]:
        self.execute(
            """
            INSERT INTO users (user_id, username, password_hash, is_guest, email, score)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, password_hash, 1 if is_guest else 0, email, score),
        )
        user = self.get_user_by_id(user_id)
        assert user is not None
        return user

    def touch_user(self, user_id: str) -> None:
        self.execute(
            "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,),
        )

    def apply_match_result(
        self,
        winner_id: str,
        loser_id: str,
        winner_delta: int,
        loser_delta: int,
    ) -> None:
        self.execute(
            "UPDATE users SET score = score + ?, wins = wins + 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
            (winner_delta, winner_id),
        )
        self.execute(
            "UPDATE users SET score = MAX(100, score + ?), losses = losses + 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
            (loser_delta, loser_id),
        )

    def insert_match(
        self,
        match_id: str,
        player1_id: str,
        player2_id: str,
        p1_score_before: int,
        p2_score_before: int,
        arena_preset: str,
    ) -> None:
        self.execute(
            """
            INSERT OR IGNORE INTO matches (
                match_id, player1_id, player2_id,
                p1_score_before, p2_score_before, arena_preset
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (match_id, player1_id, player2_id, p1_score_before, p2_score_before, arena_preset),
        )

    def finalize_match(
        self,
        match_id: str,
        winner_id: Optional[str],
        p1_delta: int,
        p2_delta: int,
        duration_seconds: float,
    ) -> None:
        self.execute(
            """
            UPDATE matches
            SET winner_id = ?, p1_score_delta = ?, p2_score_delta = ?, duration_seconds = ?
            WHERE match_id = ?
            """,
            (winner_id, p1_delta, p2_delta, duration_seconds, match_id),
        )

    def insert_movement_logs(self, rows: list[tuple[Any, ...]]) -> None:
        if not rows:
            return
        conn = self.connect()
        conn.executemany(
            """
            INSERT INTO movement_logs (
                match_id, user_id, tick, timestamp_ms,
                pos_x, pos_y, vel_x, vel_y, angle, action_flags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
