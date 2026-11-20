"""1v1 physics, collision, cooldowns, and Sudden Death — no I/O."""

from __future__ import annotations

import math
import random
from typing import Optional

from core_duel.core.entities import (
    ARENA_H,
    ARENA_W,
    DASH_COOLDOWN,
    DASH_DURATION,
    DEFAULT_HP,
    ENERGY_RING_RADIUS,
    FIRE_COOLDOWN,
    FIRE_COOLDOWN_OVERCLOCK,
    INVULN_DURATION,
    MATCH_SECONDS,
    OVERLOAD_DAMAGE,
    PULSE_DAMAGE,
    EnergyNode,
    InputState,
    MatchSnapshot,
    Obstacle,
    Particle,
    PlayerCore,
    Projectile,
)

ACCEL = 2100.0
MAX_SPEED = 290.0
FRICTION = 7.5
DASH_SPEED = 780.0
PULSE_SPEED = 540.0
BOT_NAME = "TRAINING DRONE"


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def _length(x: float, y: float) -> float:
    return math.hypot(x, y)


def _norm(x: float, y: float) -> tuple[float, float]:
    mag = _length(x, y)
    if mag <= 1e-6:
        return 0.0, 0.0
    return x / mag, y / mag


def obstacles_for_preset(preset: str) -> list[Obstacle]:
    if preset == "Twin Pillars":
        return [
            Obstacle(480, ARENA_H * 0.5, 52),
            Obstacle(800, ARENA_H * 0.5, 52),
        ]
    if preset == "Overclocked":
        return [
            Obstacle(340, 220, 40),
            Obstacle(940, 220, 40),
            Obstacle(340, 500, 40),
            Obstacle(940, 500, 40),
        ]
    return []


class GameEngine:
    def __init__(
        self,
        p1: PlayerCore,
        p2: PlayerCore,
        arena_preset: str = "Standard Containment",
        bot_controlled_p2: bool = False,
    ) -> None:
        self.preset = arena_preset
        self.overclock = arena_preset == "Overclocked"
        self.bot_p2 = bot_controlled_p2
        self.p1 = p1
        self.p2 = p2
        self.p1.facing_x, self.p1.facing_y = 1.0, 0.0
        self.p2.facing_x, self.p2.facing_y = -1.0, 0.0
        self.p1.angle = 0.0
        self.p2.angle = math.pi
        self.projectiles: list[Projectile] = []
        self.particles: list[Particle] = []
        self.obstacles = obstacles_for_preset(arena_preset)
        self.node = EnergyNode()
        self.time_left = MATCH_SECONDS
        self.sudden_death = False
        self.wall_inset = 36.0
        self.tick = 0
        self.over = False
        self.winner_id: Optional[str] = None
        self.last_events: list[str] = []
        self.rng = random.Random(0xC0DE)

    def reset_positions(self) -> None:
        self.p1.x, self.p1.y = 220.0, ARENA_H * 0.5
        self.p2.x, self.p2.y = ARENA_W - 220.0, ARENA_H * 0.5
        self.p1.vx = self.p1.vy = self.p2.vx = self.p2.vy = 0.0
        self.p1.hp = self.p2.hp = DEFAULT_HP

    def step(self, dt: float, p1_input: InputState, p2_input: InputState) -> None:
        if self.over:
            return
        dt = _clamp(dt, 0.0, 0.05)
        self.last_events.clear()
        self.tick += 1
        cd_scale = 0.5 if self.sudden_death else 1.0

        if not self.sudden_death:
            self.time_left -= dt
            if self.time_left <= 0:
                self.time_left = 0.0
                if abs(self.p1.hp - self.p2.hp) > 0.5:
                    self._finish_by_hp()
                    return
                self.sudden_death = True
                self.last_events.append("sudden_death")

        if self.sudden_death:
            self.wall_inset = min(220.0, self.wall_inset + 18.0 * dt)

        if self.bot_p2:
            p2_input = self._bot_input()

        self._control(self.p1, p1_input, dt, cd_scale)
        self._control(self.p2, p2_input, dt, cd_scale)
        self._integrate(self.p1, dt)
        self._integrate(self.p2, dt)
        self._separate_players()
        self._update_node(dt)
        self._update_projectiles(dt)
        self._update_particles(dt)
        self._check_hp_ko()

    def snapshot(self) -> MatchSnapshot:
        return MatchSnapshot(
            p1=self.p1,
            p2=self.p2,
            projectiles=self.projectiles,
            node=self.node,
            obstacles=self.obstacles,
            particles=self.particles,
            time_left=self.time_left,
            sudden_death=self.sudden_death,
            wall_inset=self.wall_inset,
            winner_id=self.winner_id,
            over=self.over,
            last_events=list(self.last_events),
        )

    def _fire_cd(self) -> float:
        return FIRE_COOLDOWN_OVERCLOCK if self.overclock else FIRE_COOLDOWN

    def _control(self, player: PlayerCore, inp: InputState, dt: float, cd_scale: float) -> None:
        player.fire_cd = max(0.0, player.fire_cd - dt)
        player.dash_cd = max(0.0, player.dash_cd - dt)
        player.invuln = max(0.0, player.invuln - dt)
        if player.dash_timer > 0:
            player.dash_timer = max(0.0, player.dash_timer - dt)

        mx, my = _norm(inp.move_x, inp.move_y)
        if mx or my:
            player.facing_x, player.facing_y = mx, my
            player.angle = math.atan2(my, mx)

        if inp.aim_x is not None and inp.aim_y is not None:
            ax, ay = inp.aim_x - player.x, inp.aim_y - player.y
            if _length(ax, ay) > 8:
                player.facing_x, player.facing_y = _norm(ax, ay)
                player.angle = math.atan2(player.facing_y, player.facing_x)

        if inp.dash and player.dash_cd <= 0 and (player.facing_x or player.facing_y):
            fx, fy = _norm(player.facing_x, player.facing_y)
            player.vx, player.vy = fx * DASH_SPEED, fy * DASH_SPEED
            player.dash_timer = DASH_DURATION
            player.invuln = INVULN_DURATION
            player.dash_cd = DASH_COOLDOWN * cd_scale
            self._burst(player.x, player.y, "cyan" if player is self.p1 else "amber", 10)

        if inp.fire and player.fire_cd <= 0:
            self._spawn_pulse(player)
            player.fire_cd = self._fire_cd() * cd_scale

        if player.dash_timer <= 0:
            player.vx += mx * ACCEL * dt
            player.vy += my * ACCEL * dt
            damp = math.exp(-FRICTION * dt)
            player.vx *= damp
            player.vy *= damp
            speed = _length(player.vx, player.vy)
            if speed > MAX_SPEED:
                player.vx *= MAX_SPEED / speed
                player.vy *= MAX_SPEED / speed

    def _integrate(self, player: PlayerCore, dt: float) -> None:
        player.x += player.vx * dt
        player.y += player.vy * dt
        self._constrain_circle(player)
        for obs in self.obstacles:
            self._resolve_circles(
                player, obs.x, obs.y, obs.radius + player.radius, bounce=False
            )

    def _bounds(self) -> tuple[float, float, float, float]:
        i = self.wall_inset
        return i, i, ARENA_W - i, ARENA_H - i

    def _constrain_circle(self, body) -> None:
        left, top, right, bottom = self._bounds()
        r = body.radius
        if body.x < left + r:
            body.x = left + r
            body.vx = abs(body.vx) * 0.3
        elif body.x > right - r:
            body.x = right - r
            body.vx = -abs(body.vx) * 0.3
        if body.y < top + r:
            body.y = top + r
            body.vy = abs(body.vy) * 0.3
        elif body.y > bottom - r:
            body.y = bottom - r
            body.vy = -abs(body.vy) * 0.3

    def _resolve_circles(self, body, ox: float, oy: float, min_dist: float, bounce: bool) -> bool:
        dx, dy = body.x - ox, body.y - oy
        dist = _length(dx, dy)
        if dist >= min_dist:
            return False
        nx, ny = _norm(dx, dy) if dist > 1e-6 else (1.0, 0.0)
        overlap = min_dist - dist
        body.x += nx * overlap
        body.y += ny * overlap
        if bounce:
            vn = body.vx * nx + body.vy * ny
            if vn < 0:
                body.vx -= 2 * vn * nx
                body.vy -= 2 * vn * ny
        return True

    def _separate_players(self) -> None:
        dx = self.p2.x - self.p1.x
        dy = self.p2.y - self.p1.y
        min_d = self.p1.radius + self.p2.radius
        dist = _length(dx, dy)
        if dist >= min_d or dist < 1e-6:
            return
        nx, ny = dx / dist, dy / dist
        push = (min_d - dist) * 0.5
        self.p1.x -= nx * push
        self.p1.y -= ny * push
        self.p2.x += nx * push
        self.p2.y += ny * push

    def _spawn_pulse(self, player: PlayerCore) -> None:
        fx, fy = _norm(player.facing_x, player.facing_y)
        if fx == 0 and fy == 0:
            fx, fy = (1.0, 0.0) if player is self.p1 else (-1.0, 0.0)
        spawn_r = player.radius + 10
        self.projectiles.append(
            Projectile(
                x=player.x + fx * spawn_r,
                y=player.y + fy * spawn_r,
                vx=fx * PULSE_SPEED,
                vy=fy * PULSE_SPEED,
                owner_id=player.user_id,
                damage=PULSE_DAMAGE,
                kind="pulse",
            )
        )

    def _spawn_overload(self, player: PlayerCore, target: PlayerCore) -> None:
        fx, fy = _norm(target.x - player.x, target.y - player.y)
        if fx == 0 and fy == 0:
            fx, fy = player.facing_x, player.facing_y
        self.projectiles.append(
            Projectile(
                x=player.x + fx * (player.radius + 14),
                y=player.y + fy * (player.radius + 14),
                vx=fx * 420.0,
                vy=fy * 420.0,
                owner_id=player.user_id,
                damage=OVERLOAD_DAMAGE,
                kind="overload",
                bounces_left=0,
                radius=9.0,
            )
        )
        self.last_events.append("overload")

    def _update_node(self, dt: float) -> None:
        charge_rate = 0.70 if self.overclock else 0.42
        if not self.node.active:
            self.node.respawn_in -= dt
            if self.node.respawn_in <= 0:
                self.node.active = True
            return
        for player, rival in ((self.p1, self.p2), (self.p2, self.p1)):
            if _length(player.x - self.node.x, player.y - self.node.y) <= ENERGY_RING_RADIUS:
                player.overload_charge += charge_rate * dt
                if player.overload_charge >= 1.0:
                    player.overload_charge = 0.0
                    self._spawn_overload(player, rival)
                    self.node.active = False
                    self.node.respawn_in = 6.0 if self.overclock else 8.0
                    break
            else:
                player.overload_charge = max(0.0, player.overload_charge - 0.25 * dt)

    def _update_projectiles(self, dt: float) -> None:
        left, top, right, bottom = self._bounds()
        alive: list[Projectile] = []
        for shot in self.projectiles:
            if not shot.alive:
                continue
            shot.x += shot.vx * dt
            shot.y += shot.vy * dt
            bounced = False
            if shot.x - shot.radius < left:
                shot.x = left + shot.radius
                shot.vx = abs(shot.vx)
                bounced = True
            elif shot.x + shot.radius > right:
                shot.x = right - shot.radius
                shot.vx = -abs(shot.vx)
                bounced = True
            if shot.y - shot.radius < top:
                shot.y = top + shot.radius
                shot.vy = abs(shot.vy)
                bounced = True
            elif shot.y + shot.radius > bottom:
                shot.y = bottom - shot.radius
                shot.vy = -abs(shot.vy)
                bounced = True
            if bounced:
                if shot.bounces_left <= 0:
                    shot.alive = False
                    continue
                shot.bounces_left -= 1

            blocked = False
            for obs in self.obstacles:
                dx, dy = shot.x - obs.x, shot.y - obs.y
                if _length(dx, dy) <= obs.radius + shot.radius:
                    blocked = True
                    break
            if blocked:
                continue

            hit = False
            for target in (self.p1, self.p2):
                if target.user_id == shot.owner_id or not target.alive:
                    continue
                if _length(shot.x - target.x, shot.y - target.y) <= target.radius + shot.radius:
                    self._apply_hit(target, shot)
                    hit = True
                    break
            if not hit:
                alive.append(shot)
        self.projectiles = alive

    def _apply_hit(self, target: PlayerCore, shot: Projectile) -> None:
        if target.invuln > 0:
            return
        target.hp = max(0.0, target.hp - shot.damage)
        self._burst(target.x, target.y, "amber" if target is self.p2 else "cyan", 14)
        self.last_events.append("hit")
        if self.sudden_death:
            self.over = True
            self.winner_id = shot.owner_id
            self.last_events.append("match_over")

    def _check_hp_ko(self) -> None:
        if self.over:
            return
        if self.p1.hp <= 0 and self.p2.hp <= 0:
            self.over = True
            self.winner_id = None
            return
        if self.p1.hp <= 0:
            self.over = True
            self.winner_id = self.p2.user_id
        elif self.p2.hp <= 0:
            self.over = True
            self.winner_id = self.p1.user_id

    def _finish_by_hp(self) -> None:
        self.over = True
        if self.p1.hp > self.p2.hp:
            self.winner_id = self.p1.user_id
        elif self.p2.hp > self.p1.hp:
            self.winner_id = self.p2.user_id
        else:
            self.winner_id = None

    def _update_particles(self, dt: float) -> None:
        next_p: list[Particle] = []
        for part in self.particles:
            part.life -= dt
            if part.life <= 0:
                continue
            part.x += part.vx * dt
            part.y += part.vy * dt
            next_p.append(part)
        self.particles = next_p[:80]

    def _burst(self, x: float, y: float, color: str, count: int) -> None:
        for _ in range(count):
            ang = self.rng.random() * math.tau
            spd = 40 + self.rng.random() * 160
            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=math.cos(ang) * spd,
                    vy=math.sin(ang) * spd,
                    life=0.25 + self.rng.random() * 0.35,
                    color=color,
                    radius=1.5 + self.rng.random() * 2.0,
                )
            )

    def _bot_input(self) -> InputState:
        me, foe = self.p2, self.p1
        aim_x, aim_y = foe.x - me.x, foe.y - me.y
        dist = _length(aim_x, aim_y)
        mx, my = _norm(aim_x, aim_y)
        # strafe a little so the drone does not sit on the node forever
        mx += math.sin(self.tick * 0.03) * 0.35
        my += math.cos(self.tick * 0.02) * 0.35
        incoming = False
        for shot in self.projectiles:
            if shot.owner_id == me.user_id:
                continue
            if _length(shot.x - me.x, shot.y - me.y) < 90:
                incoming = True
                break
        fire = dist < 520 and (self.tick % 22 == 0)
        return InputState(move_x=mx, move_y=my, fire=fire, dash=incoming, aim_x=foe.x, aim_y=foe.y)

    def to_net_state(self) -> dict:
        def pack_player(p: PlayerCore) -> dict:
            return {
                "id": p.user_id,
                "x": p.x,
                "y": p.y,
                "vx": p.vx,
                "vy": p.vy,
                "a": p.angle,
                "hp": p.hp,
                "fc": p.fire_cd,
                "dc": p.dash_cd,
                "iv": p.invuln,
                "oc": p.overload_charge,
                "fx": p.facing_x,
                "fy": p.facing_y,
            }

        return {
            "t": self.tick,
            "tl": self.time_left,
            "sd": self.sudden_death,
            "wi": self.wall_inset,
            "over": self.over,
            "win": self.winner_id,
            "p1": pack_player(self.p1),
            "p2": pack_player(self.p2),
            "pr": [
                {"x": s.x, "y": s.y, "k": s.kind, "r": s.radius, "o": s.owner_id}
                for s in self.projectiles
            ],
            "na": self.node.active,
        }

    def apply_net_state(self, state: dict) -> None:
        def unpack(p: PlayerCore, d: dict) -> None:
            p.x, p.y = d["x"], d["y"]
            p.vx, p.vy = d["vx"], d["vy"]
            p.angle = d["a"]
            p.hp = d["hp"]
            p.fire_cd, p.dash_cd, p.invuln = d["fc"], d["dc"], d["iv"]
            p.overload_charge = d["oc"]
            p.facing_x, p.facing_y = d["fx"], d["fy"]

        self.tick = state["t"]
        self.time_left = state["tl"]
        self.sudden_death = state["sd"]
        self.wall_inset = state["wi"]
        self.over = state["over"]
        self.winner_id = state["win"]
        unpack(self.p1, state["p1"])
        unpack(self.p2, state["p2"])
        self.node.active = state["na"]
        self.projectiles = [
            Projectile(x=s["x"], y=s["y"], vx=0, vy=0, owner_id=s["o"], radius=s["r"], kind=s["k"])
            for s in state.get("pr", [])
        ]
