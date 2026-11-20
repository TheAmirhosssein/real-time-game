"""SQLAlchemy 2.0 mapped tables for Core Duel."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MatchmakingQueue(Base):
    __tablename__ = "matchmaking_queue"

    queue_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), unique=True, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    arena_preset: Mapped[str] = mapped_column(String(64), default="Standard Containment")
    status: Mapped[str] = mapped_column(String(16), default="SEARCHING")
    matched_room_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Match(Base):
    __tablename__ = "matches"

    match_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    player1_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    player2_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    winner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    p1_score_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p2_score_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p1_score_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p2_score_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    arena_preset: Mapped[str | None] = mapped_column(String(64), nullable=True)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MovementLog(Base):
    __tablename__ = "movement_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.match_id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pos_x: Mapped[float] = mapped_column(Float, nullable=False)
    pos_y: Mapped[float] = mapped_column(Float, nullable=False)
    vel_x: Mapped[float] = mapped_column(Float, nullable=False)
    vel_y: Mapped[float] = mapped_column(Float, nullable=False)
    angle: Mapped[float] = mapped_column(Float, nullable=False)
    action_flags: Mapped[str | None] = mapped_column(Text, nullable=True)
