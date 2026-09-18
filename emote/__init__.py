import dbus
import os
import sys
import gi
from setproctitle import setproctitle

gi.require_version("Gtk", "3.0")
gi.require_version("Keybinder", "3.0")
from gi.repository import Gtk, Keybinder

from emote import picker, css, emojis, settings, config

gtk_settings = Gtk.Settings.get_default()


class EmoteApplication(Gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, application_id="com.tomjwatson.Emote", **kwargs)

        self.activated = False
        self.picker_window = None

    def start_daemon(self):
        setproctitle("emote")
        self.settings = settings.load()

        if not config.is_wayland:
            Keybinder.init()
            self.set_accelerator()

        css.load_css()
        emojis.init()

        self.activated = True

        # The first time the app launches, open the picker and show the
        # guide
        if not self.settings.shown_welcome:
            self.create_picker_window(True)
            self.settings.shown_welcome = True
            self.settings.save()

        if config.is_flatpak:
            self.flatpak_autostart()
        self.set_theme()

        # Run the main gtk event loop - this prevents the app from quitting
        Gtk.main()

    def flatpak_autostart(self):
        """Enable autostart in background for flatpak app"""
        try:
            bus = dbus.SessionBus()
            obj = bus.get_object(
                "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
            )
            inter = dbus.Interface(obj, "org.freedesktop.portal.Background")
            res = inter.RequestBackground(
                "",
                {
                    "reason": "Emote autostart",
                    "autostart": True,
                    "background": True,
                    "commandline": dbus.Array(["emote"]),
                },
            )
        except Exception as e:
            print("Failed to enable autostart:", e)

    def set_accelerator(self):
        """Register global shortcut for invoking the emoji picker"""
        accel_string = self.settings.accelerator

        if accel_string:
            Keybinder.bind(accel_string, self.handle_accelerator)

    def set_theme(self):
        """Set the GTK theme to be used for the app windows"""
        theme = self.settings.theme

        print(
            f"Setting theme New=[{theme}] "
            f'Current=[{gtk_settings.get_property("gtk-theme-name")}]'
        )
        if theme != settings.DEFAULT_THEME:
            print(f"Setting theme to {theme}")
            gtk_settings.set_property("gtk-theme-name", theme)
        else:
            gtk_settings.reset_property("gtk-theme-name")

    def unset_accelerator(self, accel_string):
        if accel_string:
            Keybinder.unbind(accel_string)

    def handle_accelerator(self, keystring):
        if self.picker_window:
            self.picker_window.destroy()
        else:
            self.create_picker_window()

    def update_accelerator(self, accel_string):
        accel_string = accel_string or ""
        accel_label = Gtk.accelerator_get_label(*Gtk.accelerator_parse(accel_string))
        print(f"Updating global shortcut to {accel_label or 'none'}")
        self.unset_accelerator(self.settings.accelerator)
        self.settings.accelerator = accel_string
        self.settings.save()
        self.set_accelerator()

    def update_theme(self, theme):
        self.settings.theme = theme
        self.settings.save()
        self.set_theme()

    def update_skintone_index(self, skintone_index):
        self.settings.skintone_index = skintone_index
        self.settings.save()

    def create_picker_window(self, show_welcome=False):
        if self.picker_window:
            self.picker_window.destroy()

        old_accelerator = self.settings.accelerator
        self.settings = settings.load()
        if not config.is_wayland and self.settings.accelerator != old_accelerator:
            self.unset_accelerator(old_accelerator)
            self.set_accelerator()
        self.set_theme()

        self.picker_window = picker.EmojiPicker(
            Keybinder.get_current_event_time(), self, show_welcome
        )
        self.picker_window.connect("destroy", self.handle_picker_destroy)

    def handle_picker_destroy(self, *args):
        self.picker_window = None

    def do_activate(self):
        if not self.activated:
            print("Launching emote daemon")
            self.start_daemon()
        else:
            print("Second instance launched")
            self.create_picker_window()


def main():
    app = EmoteApplication()
    app.run(sys.argv)
