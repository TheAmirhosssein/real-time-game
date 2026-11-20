"""Canvas arena, keyboard/mouse input, HUD, pause and post-match overlays."""

from __future__ import annotations

import math
from typing import Optional

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from core_duel.core.entities import ARENA_H, ARENA_W, InputState, MATCH_SECONDS
from core_duel.core.engine import GameEngine
from core_duel.core.telemetry import TelemetryBuffer
from core_duel.palette import (
    ACCENT_AMBER,
    ACCENT_CYAN,
    BG_VOID,
    BORDER_CONDUIT,
    STATE_ERROR,
    STATE_SUCCESS,
    SURFACE_ELEVATED,
    SURFACE_PANEL,
    TEXT_MUTED,
    TEXT_PRIMARY,
)
from core_duel.services.matchmaking import elo_deltas
from core_duel.ui.widgets import CyberButton, PanelCard


class ArenaView(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.engine: Optional[GameEngine] = None
        self.bind(pos=self.redraw, size=self.redraw)

    def arena_rect(self) -> tuple[float, float, float, float]:
        aspect = ARENA_W / ARENA_H
        w, h = max(self.width, 1), max(self.height, 1)
        if w / h > aspect:
            rh, rw = h, h * aspect
        else:
            rw, rh = w, w / aspect
        ox = self.x + (w - rw) / 2
        oy = self.y + (h - rh) / 2
        return ox, oy, rw, rh

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        ox, oy, rw, rh = self.arena_rect()
        return ox + (x / ARENA_W) * rw, oy + (y / ARENA_H) * rh

    def to_arena(self, sx: float, sy: float) -> tuple[float, float]:
        ox, oy, rw, rh = self.arena_rect()
        return (sx - ox) / rw * ARENA_W, (sy - oy) / rh * ARENA_H

    def s(self, value: float) -> float:
        _ox, _oy, rw, _rh = self.arena_rect()
        return value * (rw / ARENA_W)

    def redraw(self, *_args):
        engine = self.engine
        self.canvas.clear()
        ox, oy, rw, rh = self.arena_rect()
        with self.canvas:
            Color(*BG_VOID)
            Rectangle(pos=self.pos, size=self.size)
            Color(*BORDER_CONDUIT)
            for gx in range(0, int(ARENA_W), 64):
                x, _y = self.to_screen(gx, 0)
                Line(points=[x, oy, x, oy + rh], width=1)
            for gy in range(0, int(ARENA_H), 64):
                _x, y = self.to_screen(0, gy)
                Line(points=[ox, y, ox + rw, y], width=1)
            Color(*ACCENT_CYAN, 0.35 if not engine else 0.45)
            Line(rectangle=(ox, oy, rw, rh), width=1.4)

            if engine is None:
                return

            inset = engine.wall_inset
            ix0, iy0 = self.to_screen(inset, inset)
            ix1, iy1 = self.to_screen(ARENA_W - inset, ARENA_H - inset)
            Color(*(STATE_ERROR if engine.sudden_death else BORDER_CONDUIT))
            Line(rectangle=(ix0, iy0, ix1 - ix0, iy1 - iy0), width=1.6)

            node = engine.node
            nx, ny = self.to_screen(node.x, node.y)
            nr = self.s(node.radius)
            if node.active:
                Color(0.0, 0.9, 1.0, 0.12)
                Ellipse(pos=(nx - nr, ny - nr), size=(nr * 2, nr * 2))
                Color(*ACCENT_CYAN, 0.8)
                Line(circle=(nx, ny, nr), width=1.3)
            else:
                Color(*TEXT_MUTED, 0.25)
                Line(circle=(nx, ny, nr), width=1)

            for obs in engine.obstacles:
                cx, cy = self.to_screen(obs.x, obs.y)
                rr = self.s(obs.radius)
                Color(*SURFACE_ELEVATED)
                Ellipse(pos=(cx - rr, cy - rr), size=(rr * 2, rr * 2))
                Color(*BORDER_CONDUIT)
                Line(circle=(cx, cy, rr), width=1.2)

            for part in engine.particles:
                px, py = self.to_screen(part.x, part.y)
                pr = self.s(part.radius)
                col = ACCENT_CYAN if part.color == "cyan" else ACCENT_AMBER
                Color(*col[:3], min(1.0, part.life * 2.5))
                Ellipse(pos=(px - pr, py - pr), size=(pr * 2, pr * 2))

            for shot in engine.projectiles:
                sx, sy = self.to_screen(shot.x, shot.y)
                sr = self.s(shot.radius)
                col = ACCENT_AMBER if shot.kind == "overload" else ACCENT_CYAN
                if shot.owner_id == engine.p2.user_id and shot.kind != "overload":
                    col = ACCENT_AMBER
                Color(*col)
                Ellipse(pos=(sx - sr, sy - sr), size=(sr * 2, sr * 2))

            self._draw_core(engine.p1, ACCENT_CYAN)
            self._draw_core(engine.p2, ACCENT_AMBER)

    def _draw_core(self, player, color):
        cx, cy = self.to_screen(player.x, player.y)
        r = self.s(player.radius)
        glow = r * (1.35 if player.invuln > 0 else 1.15)
        Color(*color[:3], 0.22)
        Ellipse(pos=(cx - glow, cy - glow), size=(glow * 2, glow * 2))
        Color(*color)
        Ellipse(pos=(cx - r, cy - r), size=(r * 2, r * 2))
        Color(*BG_VOID)
        inner = r * 0.45
        Ellipse(pos=(cx - inner, cy - inner), size=(inner * 2, inner * 2))
        fx = math.cos(player.angle) * r * 1.4
        fy = math.sin(player.angle) * r * 1.4
        Color(*TEXT_PRIMARY)
        Line(points=[cx, cy, cx + fx, cy + fy], width=1.4)
        if player.overload_charge > 0.05:
            Color(*STATE_SUCCESS, 0.9)
            Line(circle=(cx, cy, r + self.s(4)), width=1.2)


class GameScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.engine: Optional[GameEngine] = None
        self.telemetry: Optional[TelemetryBuffer] = None
        self.mode = "local"
        self.match_id = ""
        self.is_host = True
        self.net = None
        self.paused = False
        self.finished = False
        self._keys: set[str] = set()
        self._clock = None
        self._keyboard = None
        self._mouse = (0.0, 0.0)
        self._result_applied = False

        root = FloatLayout()
        self.arena = ArenaView()
        root.add_widget(self.arena)

        self.hud = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=56,
            pos_hint={"top": 1},
            padding=[12, 6],
            spacing=8,
        )
        self.p1_hud = Label(halign="left", valign="middle", markup=True)
        self.timer_hud = Label(halign="center", valign="middle", markup=True, bold=True)
        self.p2_hud = Label(halign="right", valign="middle", markup=True)
        for lab in (self.p1_hud, self.timer_hud, self.p2_hud):
            lab.color = TEXT_PRIMARY
            lab.bind(size=lambda inst, _v: setattr(inst, "text_size", inst.size))
        self.hud.add_widget(self.p1_hud)
        self.hud.add_widget(self.timer_hud)
        self.hud.add_widget(self.p2_hud)
        root.add_widget(self.hud)

        self.hint = Label(
            text="ESC pause  •  P1 WASD/SPACE/L-SHIFT  •  aim with mouse",
            size_hint=(1, None),
            height=28,
            pos_hint={"y": 0},
            color=TEXT_MUTED,
            font_size="12sp",
        )
        root.add_widget(self.hint)

        self.pause_card = self._build_pause()
        self.result_card = self._build_result()
        root.add_widget(self.pause_card)
        root.add_widget(self.result_card)
        self.add_widget(root)

        self.bind(size=self._layout_overlays, pos=self._layout_overlays)

    def _build_pause(self) -> PanelCard:
        card = PanelCard(
            orientation="vertical",
            size_hint=(None, None),
            size=(360, 210),
            padding=18,
            spacing=10,
            opacity=0,
            disabled=True,
        )
        card.add_widget(Label(text="PAUSED", bold=True, font_size="22sp", size_hint_y=None, height=36))
        resume = CyberButton(text="RESUME", size_hint_y=None, height=44, bg_color=list(ACCENT_CYAN))
        resume.color = (0.02, 0.05, 0.08, 1)
        resume.bind(on_release=lambda *_: self.set_paused(False))
        forfeit = CyberButton(
            text="FORFEIT / RETURN TO LOBBY",
            size_hint_y=None,
            height=44,
            bg_color=list(SURFACE_ELEVATED),
        )
        forfeit.bind(on_release=lambda *_: self.forfeit())
        card.add_widget(resume)
        card.add_widget(forfeit)
        return card

    def _build_result(self) -> PanelCard:
        card = PanelCard(
            orientation="vertical",
            size_hint=(None, None),
            size=(420, 280),
            padding=18,
            spacing=8,
            opacity=0,
            disabled=True,
        )
        self.result_title = Label(text="MATCH COMPLETE", bold=True, font_size="22sp", size_hint_y=None, height=36)
        self.result_delta = Label(text="", font_size="16sp", size_hint_y=None, height=28)
        self.result_stats = Label(text="", color=TEXT_MUTED, font_size="13sp")
        again = CyberButton(text="PLAY AGAIN", size_hint_y=None, height=42, bg_color=list(ACCENT_CYAN))
        again.color = (0.02, 0.05, 0.08, 1)
        again.bind(on_release=lambda *_: self.play_again())
        lobby = CyberButton(text="LOBBY", size_hint_y=None, height=42, bg_color=list(SURFACE_ELEVATED))
        lobby.bind(on_release=lambda *_: self.return_lobby())
        for w in (self.result_title, self.result_delta, self.result_stats, again, lobby):
            card.add_widget(w)
        return card

    def _layout_overlays(self, *_args):
        for card in (self.pause_card, self.result_card):
            card.center = self.center

    def on_pre_enter(self, *args):
        app = App.get_running_app()
        session = app.match_session
        if not session:
            self.manager.current = "lobby_screen"
            return
        self.engine = session["engine"]
        self.telemetry = session["telemetry"]
        self.mode = session["mode"]
        self.match_id = session["match_id"]
        self.is_host = session["is_host"]
        self.net = session.get("net")
        self.arena.engine = self.engine
        self.paused = False
        self.finished = False
        self._result_applied = False
        self._keys.clear()
        self.pause_card.opacity = 0
        self.pause_card.disabled = True
        self.result_card.opacity = 0
        self.result_card.disabled = True
        if self.mode == "local":
            self.hint.text = "P1 WASD/SPACE/L-SHIFT   •   P2 Arrows/ENTER/R-SHIFT   •   ESC pause"
        elif self.mode == "bot":
            self.hint.text = "P1 WASD/SPACE/L-SHIFT + mouse aim   •   ESC pause   •   training drone online"
        else:
            self.hint.text = "WASD move  •  SPACE fire  •  L-SHIFT dash  •  mouse aim  •  ESC pause"

        self._keyboard = Window.request_keyboard(self._keyboard_closed, self, "text")
        if self._keyboard:
            self._keyboard.bind(on_key_down=self._on_key_down, on_key_up=self._on_key_up)
        Window.bind(
            mouse_pos=self._on_mouse,
            on_key_down=self._on_window_key,
            on_key_up=self._on_window_key_up,
        )
        self._stop_clock()
        self._clock = Clock.schedule_interval(self.update, 1.0 / 60.0)
        self.arena.redraw()

    def on_leave(self, *args):
        self._stop_clock()
        Window.unbind(
            mouse_pos=self._on_mouse,
            on_key_down=self._on_window_key,
            on_key_up=self._on_window_key_up,
        )
        if self._keyboard:
            self._keyboard.unbind(on_key_down=self._on_key_down, on_key_up=self._on_key_up)
            self._keyboard = None
        if self.net:
            self.net.close()
            self.net = None
        app = App.get_running_app()
        if app.current_user:
            app.matchmaking.cancel(app.current_user["user_id"])

    def _stop_clock(self):
        if self._clock is not None:
            Clock.unschedule(self._clock)
            self._clock = None

    def _keyboard_closed(self):
        if self._keyboard:
            self._keyboard.unbind(on_key_down=self._on_key_down, on_key_up=self._on_key_up)
            self._keyboard = None

    def _on_mouse(self, _window, pos):
        self._mouse = pos

    def _key_name(self, keycode) -> str:
        if isinstance(keycode, (tuple, list)) and len(keycode) > 1:
            return str(keycode[1])
        return str(keycode)

    def _on_key_down(self, _keyboard, keycode, _text, _modifiers):
        name = self._key_name(keycode)
        if name == "escape":
            return True
        self._keys.add(name)
        return True

    def _on_key_up(self, _keyboard, keycode):
        self._keys.discard(self._key_name(keycode))
        return True

    _WINDOW_KEYS = {
        273: "up",
        274: "down",
        275: "right",
        276: "left",
        13: "enter",
        303: "rshift",
        304: "shift",
        32: "space",
        27: "escape",
        97: "a",
        100: "d",
        115: "s",
        119: "w",
    }

    def _on_window_key(self, _window, key, _scancode, _codepoint, _modifiers):
        name = self._WINDOW_KEYS.get(key)
        if not name:
            return
        if name == "escape":
            if "escape" not in self._keys and not self.finished:
                self.set_paused(not self.paused)
            self._keys.add("escape")
            return
        self._keys.add(name)

    def _on_window_key_up(self, _window, key, *_args):
        name = self._WINDOW_KEYS.get(key)
        if name:
            self._keys.discard(name)

    def set_paused(self, value: bool):
        if self.finished:
            return
        self.paused = value
        self.pause_card.opacity = 1 if value else 0
        self.pause_card.disabled = not value
        self._layout_overlays()

    def forfeit(self):
        if self.engine and not self.finished:
            self.engine.over = True
            self.engine.winner_id = self.engine.p2.user_id
        self._complete_match()
        self.return_lobby()

    def play_again(self):
        app = App.get_running_app()
        session = app.match_session
        if not session:
            self.return_lobby()
            return
        self.return_lobby()
        lobby = self.manager.get_screen("lobby_screen")
        if session["mode"] == "local":
            lobby.local_match()
        else:
            lobby.find_match()

    def return_lobby(self):
        self.manager.current = "lobby_screen"

    def _axis(self, neg: str, pos: str) -> float:
        value = 0.0
        if neg in self._keys:
            value -= 1.0
        if pos in self._keys:
            value += 1.0
        return value

    def _p1_input(self) -> InputState:
        mx = self._axis("a", "d")
        my = self._axis("s", "w")
        fire = "space" in self._keys
        dash = "shift" in self._keys or "lshift" in self._keys
        ax = ay = None
        if self.mode != "local":
            ax, ay = self.arena.to_arena(*self._mouse)
        return InputState(mx, my, fire, dash, ax, ay)

    def _p2_input(self) -> InputState:
        if self.mode != "local":
            return InputState()
        mx = self._axis("left", "right")
        my = self._axis("down", "up")
        fire = "enter" in self._keys
        dash = "rshift" in self._keys
        return InputState(mx, my, fire, dash)

    def update(self, dt):
        engine = self.engine
        if engine is None:
            return
        if self.paused or self.finished:
            self.arena.redraw()
            self._refresh_hud()
            return

        p1 = self._p1_input()
        p2 = self._p2_input()

        if self.mode == "net" and self.net:
            if not self.net.connected.is_set():
                self.timer_hud.text = "LINKING..."
                self.arena.redraw()
                return
            if self.is_host:
                for msg in self.net.drain():
                    if msg.get("type") == "input":
                        d = msg.get("i", {})
                        p2 = InputState(
                            d.get("mx", 0),
                            d.get("my", 0),
                            d.get("f", False),
                            d.get("d", False),
                            d.get("ax"),
                            d.get("ay"),
                        )
                engine.step(dt, p1, p2)
                self.net.send({"type": "state", "s": engine.to_net_state()})
            else:
                self.net.send(
                    {
                        "type": "input",
                        "i": {
                            "mx": p1.move_x,
                            "my": p1.move_y,
                            "f": p1.fire,
                            "d": p1.dash,
                            "ax": p1.aim_x,
                            "ay": p1.aim_y,
                        },
                    }
                )
                for msg in self.net.drain():
                    if msg.get("type") == "state":
                        engine.apply_net_state(msg["s"])
        else:
            engine.step(dt, p1, p2)

        if self.telemetry and (self.mode != "net" or self.is_host):
            self.telemetry.record_tick(
                engine.tick, engine.p1, engine.p2, p1, p2, engine.last_events, engine.p1.user_id
            )

        if engine.over:
            self._complete_match()

        self.arena.redraw()
        self._refresh_hud()

    def _refresh_hud(self):
        engine = self.engine
        if engine is None:
            return
        p1, p2 = engine.p1, engine.p2
        self.p1_hud.text = (
            f"[color=00e5ff]{p1.callsign}[/color]\n"
            f"HP {p1.hp:0.0f}/100   DASH {int(p1.energy_ratio * 100)}%"
        )
        self.p2_hud.text = (
            f"[color=ff6b00]{p2.callsign}[/color]\n"
            f"HP {p2.hp:0.0f}/100   DASH {int(p2.energy_ratio * 100)}%"
        )
        if engine.sudden_death:
            self.timer_hud.color = STATE_ERROR
            self.timer_hud.text = "SUDDEN DEATH"
        else:
            self.timer_hud.color = TEXT_PRIMARY
            secs = max(0, int(math.ceil(engine.time_left)))
            self.timer_hud.text = f"{secs:02d}s"
        self.canvas.after.clear()
        with self.canvas.after:
            # HP bars under HUD labels
            bar_y = self.height - 8
            self._bar(16, bar_y, 280, p1.hp / 100.0, ACCENT_CYAN)
            self._bar(self.width - 296, bar_y, 280, p2.hp / 100.0, ACCENT_AMBER)

    def _bar(self, x, y, w, ratio, color):
        Color(*SURFACE_PANEL)
        RoundedRectangle(pos=(x, y - 52), size=(w, 8), radius=[3])
        Color(*color)
        RoundedRectangle(pos=(x, y - 52), size=(max(0, w * ratio), 8), radius=[3])

    def _complete_match(self):
        if self._result_applied or self.engine is None:
            return
        self._result_applied = True
        self.finished = True
        self.paused = False
        self.pause_card.opacity = 0
        self.pause_card.disabled = True
        engine = self.engine
        app = App.get_running_app()
        if self.telemetry:
            self.telemetry.flush()
        p1, p2 = engine.p1, engine.p2
        winner_id = engine.winner_id
        persist = self.mode != "net" or self.is_host
        p1_delta = p2_delta = 0
        if persist:
            if winner_id == p1.user_id:
                p1_delta, p2_delta = elo_deltas(p1.score, p2.score)
                app.db.apply_match_result(p1.user_id, p2.user_id, p1_delta, p2_delta)
            elif winner_id == p2.user_id:
                p2_delta, p1_delta = elo_deltas(p2.score, p1.score)
                app.db.apply_match_result(p2.user_id, p1.user_id, p2_delta, p1_delta)
            duration = MATCH_SECONDS - engine.time_left if not engine.sudden_death else MATCH_SECONDS + 0.01
            app.db.finalize_match(self.match_id, winner_id, p1_delta, p2_delta, max(0.0, duration))
        else:
            if winner_id == p1.user_id:
                p1_delta, p2_delta = elo_deltas(p1.score, p2.score)
            elif winner_id == p2.user_id:
                p2_delta, p1_delta = elo_deltas(p2.score, p1.score)

        local = app.current_user or {}
        local_id = local.get("user_id")
        if winner_id is None:
            title = "DRAW"
            delta_txt = "0 MMR"
        elif winner_id == local_id:
            title = "VICTORY"
            d = p1_delta if local_id == p1.user_id else p2_delta
            delta_txt = f"+{d} MMR"
            self.result_delta.color = STATE_SUCCESS
        else:
            title = "DEFEAT"
            d = p1_delta if local_id == p1.user_id else p2_delta
            delta_txt = f"{d} MMR"
            self.result_delta.color = STATE_ERROR
        if winner_id == local_id or (winner_id is None):
            if winner_id is None:
                self.result_delta.color = TEXT_MUTED
        self.result_title.text = title
        self.result_delta.text = delta_txt
        stats = self.telemetry.summary(local_id == p1.user_id) if self.telemetry else {}
        self.result_stats.text = (
            f"Shots {stats.get('shots', 0)}   •   Hits {stats.get('hits', 0)}   •   "
            f"Accuracy {stats.get('accuracy', 0):0.0f}%   •   Dashes {stats.get('dashes', 0)}"
        )
        self.result_card.opacity = 1
        self.result_card.disabled = False
        self._layout_overlays()
        if local_id:
            fresh = app.auth.refresh(local_id)
            if fresh:
                app.current_user = fresh
