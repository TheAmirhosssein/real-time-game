from kivy.app import App
from kivy.properties import ListProperty, StringProperty
from kivy.uix.screenmanager import Screen

from core_duel.palette import STATE_ERROR, STATE_SUCCESS
from core_duel.services.auth_service import AuthError


class RegisterScreen(Screen):
    status_text = StringProperty("")
    status_color = ListProperty(list(STATE_ERROR))

    def on_pre_enter(self, *args):
        self.status_text = ""

    def go_login(self):
        self.manager.current = "login_screen"

    def do_register(self):
        app = App.get_running_app()
        try:
            user = app.auth.register(
                self.ids.callsign.text,
                self.ids.email.text,
                self.ids.password.text,
                self.ids.confirm.text,
            )
        except AuthError as exc:
            self.status_color = list(STATE_ERROR)
            self.status_text = str(exc)
            return
        self.status_color = list(STATE_SUCCESS)
        self.status_text = "Pilot registered. Starting rating 1000 MMR."
        app.enter_lobby(user)
