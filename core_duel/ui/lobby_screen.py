from kivy.app import App
from kivy.clock import Clock
from kivy.properties import ListProperty, StringProperty
from kivy.uix.screenmanager import Screen

from core_duel.palette import ACCENT_AMBER, STATE_SUCCESS
from core_duel.services.matchmaking import ARENA_PRESETS


BOT_FALLBACK_SECONDS = 22.0


class LobbyScreen(Screen):
    callsign = StringProperty("—")
    badge = StringProperty("GUEST")
    mmr_text = StringProperty("1000 MMR")
    record_text = StringProperty("0 W  /  0 L")
    queue_status = StringProperty("Standby. Select an arena and queue for a duel.")
    queue_detail = StringProperty("")
    slot2_name = StringProperty("SEARCHING...")
    slot2_meta = StringProperty("Awaiting opponent lock")
    slot2_ready = StringProperty("IDLE")
    slot1_name = StringProperty("—")
    slot1_meta = StringProperty("—")
    slot2_color = ListProperty(list(ACCENT_AMBER))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._poll = None
        self._searching = False
        self._bot_armed = False

    def on_pre_enter(self, *args):
        self._refresh_user()
        self._reset_versus()
        spinner = self.ids.arena_spinner
        spinner.values = list(ARENA_PRESETS)
        if spinner.text not in ARENA_PRESETS:
            spinner.text = ARENA_PRESETS[0]

    def on_leave(self, *args):
        self._stop_poll()
        if self._searching:
            app = App.get_running_app()
            if app.current_user:
                app.matchmaking.cancel(app.current_user["user_id"])
            self._searching = False

    def _app(self):
        return App.get_running_app()

    def _refresh_user(self):
        app = self._app()
        user = app.current_user
        if not user:
            return
        fresh = app.auth.refresh(user["user_id"]) or user
        app.current_user = fresh
        self.callsign = fresh["username"]
        self.badge = "GUEST" if fresh["is_guest"] else "REGISTERED"
        self.mmr_text = f"{fresh['score']} MMR"
        self.record_text = f"{fresh['wins']} W  /  {fresh['losses']} L"
        self.slot1_name = fresh["username"]
        self.slot1_meta = f"{fresh['score']} MMR"

    def _reset_versus(self):
        self.slot2_name = "SEARCHING..."
        self.slot2_meta = "Awaiting opponent lock"
        self.slot2_ready = "IDLE"
        self.slot2_color = list(ACCENT_AMBER)
        self.queue_status = "Standby. Select an arena and queue for a duel."
        self.queue_detail = ""

    def _stop_poll(self):
        if self._poll is not None:
            Clock.unschedule(self._poll)
            self._poll = None

    def logout(self):
        self._stop_poll()
        self._searching = False
        app = self._app()
        if app.current_user:
            app.matchmaking.cancel(app.current_user["user_id"])
        app.current_user = None
        self.manager.current = "login_screen"

    def find_match(self):
        app = self._app()
        user = app.current_user
        if not user:
            return
        self._refresh_user()
        user = app.current_user
        self._searching = True
        self._bot_armed = False
        app.matchmaking.enqueue(user, self.ids.arena_spinner.text)
        self.queue_status = "Entered score-range queue."
        self.slot2_ready = "SEARCHING..."
        self._stop_poll()
        self._poll = Clock.schedule_interval(self._on_poll, 0.4)

    def cancel_search(self):
        app = self._app()
        if app.current_user:
            app.matchmaking.cancel(app.current_user["user_id"])
        self._searching = False
        self._stop_poll()
        self._reset_versus()

    def local_match(self):
        app = self._app()
        user = app.current_user
        if not user:
            return
        self.cancel_search()
        rival = app.ensure_local_rival()
        match_id = app.matchmaking.create_local_match(
            user, rival, self.ids.arena_spinner.text
        )
        app.start_match(
            match_id=match_id,
            opponent=rival,
            mode="local",
            arena_preset=self.ids.arena_spinner.text,
            is_host=True,
        )

    def _on_poll(self, _dt):
        app = self._app()
        user = app.current_user
        if not user or not self._searching:
            return
        status = app.matchmaking.poll(user["user_id"])
        self.queue_detail = (
            f"Elapsed {status.elapsed:0.0f}s   •   Searching: "
            f"{status.bracket_low} – {status.bracket_high} MMR..."
        )
        self.queue_status = f"Bracket ±{status.range_limit}  •  {status.arena_preset}"

        if status.matched and status.opponent_id:
            opponent = app.db.get_user_by_id(status.opponent_id)
            if opponent:
                self._lock_opponent(opponent)
                self._stop_poll()
                self._searching = False
                app.start_match(
                    match_id=status.match_id,
                    opponent=opponent,
                    mode="net",
                    arena_preset=status.arena_preset,
                    is_host=status.is_host,
                    room_endpoint=status.room_endpoint,
                )
                return

        if status.elapsed >= BOT_FALLBACK_SECONDS and not self._bot_armed:
            self._bot_armed = True
            self._start_bot_fallback()

    def _lock_opponent(self, opponent):
        self.slot2_name = opponent["username"]
        self.slot2_meta = f"{opponent['score']} MMR"
        self.slot2_ready = "READY"
        self.slot2_color = list(STATE_SUCCESS)
        self.queue_status = "Match found. Transferring to containment..."

    def _start_bot_fallback(self):
        app = self._app()
        user = app.current_user
        if not user:
            return
        app.matchmaking.cancel(user["user_id"])
        bot = app.ensure_training_drone()
        self._lock_opponent(bot)
        match_id = app.matchmaking.create_local_match(
            user, bot, self.ids.arena_spinner.text
        )
        self._searching = False
        self._stop_poll()
        app.start_match(
            match_id=match_id,
            opponent=bot,
            mode="bot",
            arena_preset=self.ids.arena_spinner.text,
            is_host=True,
        )
