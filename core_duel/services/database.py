"""PostgreSQL access via SQLAlchemy 2.0 — schema init, user CRUD, batch logs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from core_duel.services.models import Base, Match, MatchmakingQueue, MovementLog, User
from core_duel.settings import DATABASE_URL


def user_to_dict(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "is_guest": bool(user.is_guest),
        "score": int(user.score),
        "wins": int(user.wins),
        "losses": int(user.losses),
        "email": user.email,
    }


class DatabaseManager:
    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url or DATABASE_URL
        self.engine = create_engine(
            self.url, pool_pre_ping=True, pool_size=5, max_overflow=10
        )
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self._migrate()

    def _migrate(self) -> None:
        # Epoch milliseconds exceed 32-bit INTEGER; widen in-place for existing DBs.
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE movement_logs "
                    "ALTER COLUMN timestamp_ms TYPE BIGINT"
                )
            )

    def session(self) -> Session:
        return self.Session()

    def get_user_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        with self.session() as s:
            user = s.get(User, user_id)
            return user_to_dict(user) if user else None

    def get_user_by_username(self, username: str) -> Optional[User]:
        with self.session() as s:
            return s.scalar(
                select(User).where(
                    func.lower(User.username) == username.strip().lower()
                )
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
        user = User(
            user_id=user_id,
            username=username,
            password_hash=password_hash,
            is_guest=is_guest,
            email=email,
            score=score,
        )
        with self.session() as s:
            s.add(user)
            s.commit()
            s.refresh(user)
            return user_to_dict(user)

    def touch_user(self, user_id: str) -> None:
        with self.session() as s:
            s.execute(
                update(User)
                .where(User.user_id == user_id)
                .values(last_active=func.now())
            )
            s.commit()

    def apply_match_result(
        self,
        winner_id: str,
        loser_id: str,
        winner_delta: int,
        loser_delta: int,
    ) -> None:
        with self.session() as s:
            s.execute(
                update(User)
                .where(User.user_id == winner_id)
                .values(
                    score=User.score + winner_delta,
                    wins=User.wins + 1,
                    last_active=func.now(),
                )
            )
            s.execute(
                update(User)
                .where(User.user_id == loser_id)
                .values(
                    score=func.greatest(100, User.score + loser_delta),
                    losses=User.losses + 1,
                    last_active=func.now(),
                )
            )
            s.commit()

    def insert_match(
        self,
        match_id: str,
        player1_id: str,
        player2_id: str,
        p1_score_before: int,
        p2_score_before: int,
        arena_preset: str,
    ) -> None:
        stmt = (
            pg_insert(Match)
            .values(
                match_id=match_id,
                player1_id=player1_id,
                player2_id=player2_id,
                p1_score_before=p1_score_before,
                p2_score_before=p2_score_before,
                arena_preset=arena_preset,
            )
            .on_conflict_do_nothing(index_elements=[Match.match_id])
        )
        with self.session() as s:
            s.execute(stmt)
            s.commit()

    def get_match(self, match_id: str) -> Optional[Match]:
        with self.session() as s:
            return s.get(Match, match_id)

    def finalize_match(
        self,
        match_id: str,
        winner_id: Optional[str],
        p1_delta: int,
        p2_delta: int,
        duration_seconds: float,
    ) -> None:
        with self.session() as s:
            s.execute(
                update(Match)
                .where(Match.match_id == match_id)
                .values(
                    winner_id=winner_id,
                    p1_score_delta=p1_delta,
                    p2_score_delta=p2_delta,
                    duration_seconds=duration_seconds,
                )
            )
            s.commit()

    def insert_movement_logs(self, rows: list[tuple[Any, ...]]) -> None:
        if not rows:
            return
        payload = [
            {
                "match_id": r[0],
                "user_id": r[1],
                "tick": r[2],
                "timestamp_ms": r[3],
                "pos_x": r[4],
                "pos_y": r[5],
                "vel_x": r[6],
                "vel_y": r[7],
                "angle": r[8],
                "action_flags": r[9],
            }
            for r in rows
        ]
        with self.session() as s:
            s.execute(pg_insert(MovementLog), payload)
            s.commit()

    def upsert_queue(self, user_id: str, score: int, arena_preset: str) -> None:
        now = datetime.now(timezone.utc)
        stmt = pg_insert(MatchmakingQueue).values(
            user_id=user_id,
            score=score,
            arena_preset=arena_preset,
            status="SEARCHING",
            matched_room_id=None,
            joined_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[MatchmakingQueue.user_id],
            set_={
                "score": stmt.excluded.score,
                "arena_preset": stmt.excluded.arena_preset,
                "status": "SEARCHING",
                "matched_room_id": None,
                "joined_at": now,
            },
        )
        with self.session() as s:
            s.execute(stmt)
            s.commit()

    def delete_queue(self, user_id: str) -> None:
        with self.session() as s:
            row = s.scalar(
                select(MatchmakingQueue).where(MatchmakingQueue.user_id == user_id)
            )
            if row:
                s.delete(row)
                s.commit()

    def get_queue(self, user_id: str) -> Optional[MatchmakingQueue]:
        with self.session() as s:
            return s.scalar(
                select(MatchmakingQueue).where(MatchmakingQueue.user_id == user_id)
            )

    def publish_room(self, match_id: str, room: str) -> None:
        with self.session() as s:
            s.execute(
                update(MatchmakingQueue)
                .where(MatchmakingQueue.matched_room_id.startswith(match_id))
                .values(matched_room_id=room)
            )
            s.commit()

    def try_pair(self, user_id: str, score: int, rng: int, arena_preset: str) -> None:
        from uuid import uuid4

        with self.session() as s:
            me = s.scalar(
                select(MatchmakingQueue)
                .where(
                    MatchmakingQueue.user_id == user_id,
                    MatchmakingQueue.status == "SEARCHING",
                )
                .with_for_update()
            )
            if me is None:
                return
            query = (
                select(MatchmakingQueue)
                .where(
                    MatchmakingQueue.user_id != user_id,
                    MatchmakingQueue.status == "SEARCHING",
                    func.abs(MatchmakingQueue.score - score) <= rng,
                )
                .order_by(MatchmakingQueue.joined_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            opponent = s.scalar(query)
            if opponent is None and rng >= 500:
                opponent = s.scalar(
                    select(MatchmakingQueue)
                    .where(
                        MatchmakingQueue.user_id != user_id,
                        MatchmakingQueue.status == "SEARCHING",
                    )
                    .order_by(MatchmakingQueue.joined_at.asc())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
            if opponent is None:
                return
            match_id = str(uuid4())
            host = me if me.joined_at <= opponent.joined_at else opponent
            guest = opponent if host is me else me
            preset = me.arena_preset or arena_preset
            host.status = "MATCHED"
            guest.status = "MATCHED"
            host.matched_room_id = match_id
            guest.matched_room_id = match_id
            p1 = s.get(User, host.user_id)
            p2 = s.get(User, guest.user_id)
            s.add(
                Match(
                    match_id=match_id,
                    player1_id=host.user_id,
                    player2_id=guest.user_id,
                    p1_score_before=p1.score if p1 else score,
                    p2_score_before=p2.score if p2 else opponent.score,
                    arena_preset=preset,
                )
            )
            s.commit()
