"""Reusable cyber-arcade controls."""

from kivy.graphics import Color, Line, RoundedRectangle
from kivy.properties import ListProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

from core_duel.palette import BORDER_CONDUIT, SURFACE_ELEVATED, TEXT_MUTED, TEXT_PRIMARY


class CyberButton(Button):
    bg_color = ListProperty(list(SURFACE_ELEVATED))
    border_color = ListProperty(list(BORDER_CONDUIT))
    radius_dp = NumericProperty(6)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.color = TEXT_PRIMARY
        self.bold = True
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            bg_color=self._redraw,
            border_color=self._redraw,
            state=self._redraw,
        )
        self._redraw()

    def _redraw(self, *_args):
        self.canvas.before.clear()
        r = float(self.radius_dp)
        bg = list(self.bg_color)
        if self.state == "down":
            bg = [c * 0.75 for c in bg[:3]] + [bg[3] if len(bg) > 3 else 1]
        with self.canvas.before:
            Color(*bg)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[r])
            Color(*self.border_color)
            Line(
                rounded_rectangle=(self.x, self.y, self.width, self.height, r),
                width=1.1,
            )


class CyberInput(TextInput):
    border_color = ListProperty(list(BORDER_CONDUIT))

    def __init__(self, **kwargs):
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("foreground_color", TEXT_PRIMARY)
        kwargs.setdefault("cursor_color", TEXT_PRIMARY)
        kwargs.setdefault("hint_text_color", TEXT_MUTED)
        kwargs.setdefault("multiline", False)
        kwargs.setdefault("padding", [14, 12, 14, 12])
        kwargs.setdefault("font_size", "15sp")
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_active = ""
        self.bind(pos=self._redraw, size=self._redraw, focus=self._redraw, border_color=self._redraw)
        self._redraw()

    def _redraw(self, *_args):
        self.canvas.before.clear()
        from core_duel.palette import ACCENT_CYAN, SURFACE_ELEVATED

        border = ACCENT_CYAN if self.focus else self.border_color
        with self.canvas.before:
            Color(*SURFACE_ELEVATED)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[6])
            Color(*border)
            Line(
                rounded_rectangle=(self.x, self.y, self.width, self.height, 6),
                width=1.1,
            )


class PanelCard(BoxLayout):
    bg_color = ListProperty([0.067, 0.094, 0.153, 1])
    border_color = ListProperty(list(BORDER_CONDUIT))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, bg_color=self._redraw, border_color=self._redraw)
        self._redraw()

    def _redraw(self, *_args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[10])
            Color(*self.border_color)
            Line(
                rounded_rectangle=(self.x, self.y, self.width, self.height, 10),
                width=1.1,
            )
