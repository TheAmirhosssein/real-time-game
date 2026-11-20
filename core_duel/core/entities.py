"""Arena entities — pure dataclasses, 1280×720 logical space."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

ARENA_W = 1280.0
ARENA_H = 720.0
PLAYER_RADIUS = 22.0
PROJECTILE_RADIUS = 6.0
DEFAULT_HP = 100.0
FIRE_COOLDOWN = 0.35
FIRE_COOLDOWN_OVERCLOCK = 0.28
DASH_COOLDOWN = 2.5
DASH_DURATION = 0.15
INVULN_DURATION = 0.20
PULSE_DAMAGE = 12.0
OVERLOAD_DAMAGE = 25.0
MATCH_SECONDS = 90.0
ENERGY_RING_RADIUS = 70.0


@dataclass
class PlayerCore:
    user_id: str
    callsign: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    angle: float = 0.0
    hp: float = DEFAULT_HP
    radius: float = PLAYER_RADIUS
    fire_cd: float = 0.0
    dash_cd: float = 0.0
    dash_timer: float = 0.0
    invuln: float = 0.0
    overload_charge: float = 0.0
    facing_x: float = 1.0
    facing_y: float = 0.0
    score: int = 1000
    alive: bool = True

    @property
    def energy_ratio(self) -> float:
        return max(0.0, min(1.0, 1.0 - self.dash_cd / DASH_COOLDOWN))


@dataclass
class Projectile:
    x: float
    y: float
    vx: float
    vy: float
    owner_id: str
    radius: float = PROJECTILE_RADIUS
    bounces_left: int = 1
    damage: float = PULSE_DAMAGE
    kind: str = "pulse"
    alive: bool = True


@dataclass
class EnergyNode:
    x: float = ARENA_W * 0.5
    y: float = ARENA_H * 0.5
    radius: float = ENERGY_RING_RADIUS
    active: bool = True
    respawn_in: float = 0.0


@dataclass
class Obstacle:
    x: float
    y: float
    radius: float


@dataclass
class InputState:
    move_x: float = 0.0
    move_y: float = 0.0
    fire: bool = False
    dash: bool = False
    aim_x: Optional[float] = None
    aim_y: Optional[float] = None


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    color: str = "cyan"
    radius: float = 2.5


@dataclass
class MatchSnapshot:
    p1: PlayerCore
    p2: PlayerCore
    projectiles: list[Projectile] = field(default_factory=list)
    node: EnergyNode = field(default_factory=EnergyNode)
    obstacles: list[Obstacle] = field(default_factory=list)
    particles: list[Particle] = field(default_factory=list)
    time_left: float = MATCH_SECONDS
    sudden_death: bool = False
    wall_inset: float = 36.0
    winner_id: Optional[str] = None
    over: bool = False
    last_events: list[str] = field(default_factory=list)
