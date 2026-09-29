import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk
from emote import config

emoji_size_provider = Gtk.CssProvider()


def load_css():
    """
    Load associated CSS for the window.
    """
    css_provider = Gtk.CssProvider()

    css_provider.load_from_path(f"{config.static_dir}/style.css")

    screen = Gdk.Screen.get_default()
    styleContext = Gtk.StyleContext()
    styleContext.add_provider_for_screen(
        screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
    )
    styleContext.add_provider_for_screen(
        screen, emoji_size_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
    )


def set_emoji_size(size):
    cell = size + 5
    emoji_size_provider.load_from_data(
        f"#emoji_button {{ font-size: {size}px; "
        f"min-width: {cell}px; min-height: {cell}px; }}".encode()
    )
