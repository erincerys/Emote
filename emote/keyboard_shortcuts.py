import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from emote import config
from emote.keybinding import ButtonKeybinding
from emote.settings import SETTINGS_PATH


GRID_SIZE = 10


class KeyboardShortcuts(Gtk.Dialog):
    def __init__(self, settings, update_accelerator):
        Gtk.Dialog.__init__(
            self,
            title="Emote Keyboard Shortcuts",
            window_position=Gtk.WindowPosition.CENTER,
            resizable=False,
        )

        self.update_accelerator = update_accelerator

        header = Gtk.HeaderBar(title="Keyboard Shortcuts", show_close_button=True)
        self.set_titlebar(header)

        box = self.get_content_area()

        shortcuts_grid = Gtk.Grid(
            orientation=Gtk.Orientation.VERTICAL,
            margin=GRID_SIZE,
            row_spacing=GRID_SIZE,
        )
        shortcuts_grid.set_row_homogeneous(False)
        shortcuts_grid.set_column_homogeneous(True)

        row = 1

        if not config.is_wayland:
            open_label = Gtk.Label("Open Emoji Picker")
            open_label.set_alignment(0, 0.5)
            shortcuts_grid.attach(open_label, 1, row, 1, 1)
            open_keybinding = ButtonKeybinding()
            open_keybinding.set_size_request(150, -1)
            open_keybinding.connect("accel-edited", self.on_kb_changed)
            open_keybinding.connect("accel-cleared", self.on_kb_changed)
            open_keybinding.set_accel_string(settings.accelerator)
            shortcuts_grid.attach(open_keybinding, 2, row, 1, 1)
            row += 1

        select_label = Gtk.Label("Select Emoji")
        select_label.set_alignment(0, 0.5)
        shortcuts_grid.attach(select_label, 1, row, 1, 1)
        select_shortcut = Gtk.ShortcutsShortcut(accelerator="Return")
        shortcuts_grid.attach(select_shortcut, 2, row, 1, 1)
        row += 1

        select_multi_label = Gtk.Label("Add Emoji to Selection")
        select_multi_label.set_alignment(0, 0.5)
        shortcuts_grid.attach(select_multi_label, 1, row, 1, 1)
        select_multi_shortcut = Gtk.ShortcutsShortcut(accelerator="<Shift>+Return")
        shortcuts_grid.attach(select_multi_shortcut, 2, row, 1, 1)
        row += 1

        search_label = Gtk.Label("Focus Search")
        search_label.set_alignment(0, 0.5)
        shortcuts_grid.attach(search_label, 1, row, 1, 1)
        search_shortcut = Gtk.ShortcutsShortcut(
            accelerator=settings.shortcuts["focus_search"]
        )
        shortcuts_grid.attach(search_shortcut, 2, row, 1, 1)
        row += 1

        next_cat_label = Gtk.Label("Next Emoji Category")
        next_cat_label.set_alignment(0, 0.5)
        shortcuts_grid.attach(next_cat_label, 1, row, 1, 1)
        next_cat_shortcut = Gtk.ShortcutsShortcut(
            accelerator=settings.shortcuts["next_category"]
        )
        shortcuts_grid.attach(next_cat_shortcut, 2, row, 1, 1)
        row += 1

        prev_cat_label = Gtk.Label("Previous Emoji Category")
        prev_cat_label.set_alignment(0, 0.5)
        shortcuts_grid.attach(prev_cat_label, 1, row, 1, 1)
        prev_cat_shortcut = Gtk.ShortcutsShortcut(
            accelerator=settings.shortcuts["previous_category"]
        )
        shortcuts_grid.attach(prev_cat_shortcut, 2, row, 1, 1)
        row += 1

        close_label = Gtk.Label("Close Emoji Picker")
        close_label.set_alignment(0, 0.5)
        shortcuts_grid.attach(close_label, 1, row, 1, 1)
        close_shortcut = Gtk.ShortcutsShortcut(accelerator=settings.shortcuts["close"])
        shortcuts_grid.attach(close_shortcut, 2, row, 1, 1)

        box.pack_start(shortcuts_grid, True, True, GRID_SIZE)

        settings_path_label = Gtk.Label()
        escaped_settings_path = GLib.markup_escape_text(str(SETTINGS_PATH))
        settings_path_label.set_markup(
            f"<small>Edit in {escaped_settings_path}</small>"
        )
        settings_path_label.set_selectable(True)
        box.pack_start(settings_path_label, False, False, GRID_SIZE)

        self.show_all()
        self.present()

    def on_kb_changed(self, button_keybinding, accel_string=None, accel_label=None):
        self.update_accelerator(accel_string)
