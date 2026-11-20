"""Core Duel entry point — ScreenManager, theme tokens, service wiring."""

from __future__ import annotations

import uuid
from pathlib import Path

from kivy.config import Config

Config.set("graphics", "width", "1280")
Config.set("graphics", "height", "720")
Config.set("graphics", "minimum_width", "960")
Config.set("graphics", "minimum_height", "540")
Config.set("input", "mouse", "mouse,disable_multitouch")

from kivy.app import App
from kivy.clock import Clock
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from core_duel.core.engine import GameEngine
from core_duel.core.entities import PlayerCore
from core_duel.core.telemetry import TelemetryBuffer
from core_duel.palette import THEME
from core_duel.services.auth_service import AuthService
from core_duel.services.database import DatabaseManager
from core_duel.services.matchmaking import MatchmakingService
from core_duel.services.net import MatchSocket
from core_duel.ui.game_screen import GameScreen
from core_duel.ui.lobby_screen import LobbyScreen
from core_duel.ui.login_screen import LoginScreen
from core_duel.ui.register_screen import RegisterScreen
from core_duel.ui.widgets import CyberButton, CyberInput, PanelCard

Factory.register("CyberButton", cls=CyberButton)
Factory.register("CyberInput", cls=CyberInput)
Factory.register("PanelCard", cls=PanelCard)

UI_DIR = Path(__file__).resolve().parent / "ui"


class CoreDuelApp(App):
    title = "CORE DUEL // 1V1"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theme = THEME
        self.db = DatabaseManager()
        self.auth = AuthService(self.db)
        self.matchmaking = MatchmakingService(self.db)
        self.current_user = None
        self.match_session = None
        self._sm = None
        self._connect_poll = None

    def build(self):
        for name in (
            "theme.kv",
            "login_screen.kv",
            "register_screen.kv",
            "lobby_screen.kv",
        ):
            Builder.load_file(str(UI_DIR / name))
        sm = ScreenManager(transition=FadeTransition(duration=0.18))
        sm.add_widget(LoginScreen(name="login_screen"))
        sm.add_widget(RegisterScreen(name="register_screen"))
        sm.add_widget(LobbyScreen(name="lobby_screen"))
        sm.add_widget(GameScreen(name="game_screen"))
        self._sm = sm
        return sm

    def enter_lobby(self, user: dict):
        self.current_user = user
        if self._sm:
            self._sm.current = "lobby_screen"

    def ensure_local_rival(self) -> dict:
        existing = self.db.get_user_by_username("Local_Rival")
        if existing:
            return self.db.user_to_dict(existing)
        return self.db.insert_user(
            user_id=str(uuid.uuid4()),
            username="Local_Rival",
            password_hash=None,
            is_guest=True,
            score=1000,
        )

    def ensure_training_drone(self) -> dict:
        existing = self.db.get_user_by_username("TRAINING_DRONE")
        if existing:
            return self.db.user_to_dict(existing)
        return self.db.insert_user(
            user_id=str(uuid.uuid4()),
            username="TRAINING_DRONE",
            password_hash=None,
            is_guest=True,
            score=980,
        )

    def start_match(
        self,
        match_id: str,
        opponent: dict,
        mode: str,
        arena_preset: str,
        is_host: bool,
        room_endpoint: str | None = None,
    ) -> None:
        me = self.current_user
        assert me is not None
        if mode in ("local", "bot") or is_host:
            left, right = me, opponent
        else:
            left, right = opponent, me
        p1 = PlayerCore(
            user_id=left["user_id"],
            callsign=left["username"],
            x=220,
            y=360,
            score=left["score"],
        )
        p2 = PlayerCore(
            user_id=right["user_id"],
            callsign=right["username"],
            x=1060,
            y=360,
            score=right["score"],
        )
        engine = GameEngine(
            p1,
            p2,
            arena_preset=arena_preset,
            bot_controlled_p2=(mode == "bot"),
        )
        engine.reset_positions()
        telemetry = TelemetryBuffer(match_id, self.db)
        net = None
        if mode == "net":
            net = MatchSocket()
            if is_host:
                endpoint = net.start_host()
                self.matchmaking.publish_endpoint(me["user_id"], endpoint)
            elif room_endpoint:
                try:
                    net.connect_client(room_endpoint)
                except OSError:
                    net = None
                    mode = "bot"
                    engine.bot_p2 = True
            else:
                self.match_session = {
                    "engine": engine,
                    "telemetry": telemetry,
                    "mode": "net",
                    "match_id": match_id,
                    "is_host": False,
                    "net": net,
                    "awaiting_endpoint": True,
                }
                self._wait_for_endpoint(me["user_id"])
                if self._sm:
                    self._sm.current = "game_screen"
                return

        self.match_session = {
            "engine": engine,
            "telemetry": telemetry,
            "mode": mode,
            "match_id": match_id,
            "is_host": is_host,
            "net": net,
        }
        if self._sm:
            self._sm.current = "game_screen"

    def _wait_for_endpoint(self, user_id: str) -> None:
        if self._connect_poll is not None:
            Clock.unschedule(self._connect_poll)

        def _poll(_dt):
            status = self.matchmaking.poll(user_id)
            if status.room_endpoint and self.match_session:
                net = MatchSocket()
                try:
                    net.connect_client(status.room_endpoint)
                    self.match_session["net"] = net
                    self.match_session["awaiting_endpoint"] = False
                    if self._sm:
                        game = self._sm.get_screen("game_screen")
                        game.net = net
                except OSError:
                    pass
                Clock.unschedule(_poll)
                self._connect_poll = None

        self._connect_poll = Clock.schedule_interval(_poll, 0.25)

    def on_stop(self):
        if self.current_user:
            self.matchmaking.cancel(self.current_user["user_id"])
        if self._connect_poll is not None:
            Clock.unschedule(self._connect_poll)


def main() -> None:
    CoreDuelApp().run()


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
