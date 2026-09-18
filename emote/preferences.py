import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from emote import config


GRID_SIZE = 10
THEMES = [
    "System Default",
    "Adwaita",
    "Adwaita-dark",
    "Ambiance",
    "Ambiant-MATE",
    "Ambiant-MATE-Dark",
    "Arc",
    "Arc-Dark",
    "Arc-Darker",
    "Breeze",
    "Breeze-Dark",
    "Communitheme",
    "Communitheme-dark",
    "Communitheme-light",
    "Greybird",
    "Greybird-dark",
    "HighContrast",
    "Matcha-aliz",
    "Matcha-azul",
    "Matcha-dark-aliz",
    "Matcha-dark-azul",
    "Matcha-dark-sea",
    "Matcha-sea",
    "Materia",
    "Materia-compact",
    "Materia-dark",
    "Materia-dark-compact",
    "Materia-light",
    "Materia-light-compact",
    "Radiance",
    "Radiant-MATE",
    "Yaru",
    "Yaru-dark",
    "Yaru-light",
    "elementary",
]


class Preferences(Gtk.Dialog):
    def __init__(self, settings, update_theme, update_auto_paste):
        Gtk.Dialog.__init__(
            self,
            title="Emote Preferences",
            window_position=Gtk.WindowPosition.CENTER,
            resizable=False,
        )

        self.update_theme = update_theme
        self.update_auto_paste = update_auto_paste

        header = Gtk.HeaderBar(title="Preferences", show_close_button=True)
        self.set_titlebar(header)

        box = self.get_content_area()

        settings_grid = Gtk.Grid(
            orientation=Gtk.Orientation.VERTICAL,
            margin=GRID_SIZE,
            row_spacing=GRID_SIZE,
        )
        settings_grid.set_row_homogeneous(False)
        settings_grid.set_column_homogeneous(True)

        row = 1

        theme_label = Gtk.Label("Theme")
        theme_label.set_alignment(0, 0.5)
        settings_grid.attach(theme_label, 1, row, 1, 1)

        theme_combo = Gtk.ComboBoxText()
        theme_combo.set_entry_text_column(0)
        theme_combo.connect("changed", self.on_theme_combo_changed)
        for theme in THEMES:
            theme_combo.append_text(theme)
        theme_combo.set_active(THEMES.index(settings.theme))
        settings_grid.attach(theme_combo, 2, row, 1, 1)
        row += 1

        auto_paste_label = Gtk.Label("Paste automatically after selecting")
        auto_paste_label.set_alignment(0, 0.5)
        settings_grid.attach(auto_paste_label, 1, row, 1, 1)

        auto_paste_switch = Gtk.Switch(
            active=settings.auto_paste, halign=Gtk.Align.START
        )
        if config.is_wayland:
            auto_paste_switch.set_sensitive(False)
            auto_paste_switch.set_tooltip_text(
                "Automatic paste is not available on Wayland"
            )
        auto_paste_switch.connect("notify::active", self.on_auto_paste_changed)
        settings_grid.attach(auto_paste_switch, 2, row, 1, 1)
        row += 1

        box.pack_start(settings_grid, True, True, GRID_SIZE)

        self.show_all()
        self.present()

    def on_theme_combo_changed(self, combo):
        theme = combo.get_active_text()

        if theme is not None:
            self.update_theme(theme)

    def on_auto_paste_changed(self, switch, _property):
        self.update_auto_paste(switch.get_active())
