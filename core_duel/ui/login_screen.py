from kivy.app import App
from kivy.properties import ListProperty, StringProperty
from kivy.uix.screenmanager import Screen

from core_duel.palette import STATE_ERROR, STATE_SUCCESS
from core_duel.services.auth_service import AuthError


class LoginScreen(Screen):
    status_text = StringProperty("")
    status_color = ListProperty(list(STATE_ERROR))

    def on_pre_enter(self, *args):
        self.status_text = ""
        if hasattr(self.ids, "password"):
            self.ids.password.text = ""

    def _auth(self):
        return App.get_running_app().auth

    def do_login(self):
        try:
            user = self._auth().login(self.ids.callsign.text, self.ids.password.text)
        except AuthError as exc:
            self.status_color = list(STATE_ERROR)
            self.status_text = str(exc)
            return
        App.get_running_app().enter_lobby(user)

    def do_guest(self):
        try:
            user = self._auth().continue_as_guest()
        except AuthError as exc:
            self.status_color = list(STATE_ERROR)
            self.status_text = str(exc)
            return
        self.status_color = list(STATE_SUCCESS)
        self.status_text = f"Guest session {user['username']} online."
        App.get_running_app().enter_lobby(user)

    def go_register(self):
        self.manager.current = "register_screen"
