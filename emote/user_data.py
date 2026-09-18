import os
from pathlib import Path
import shelve

from emote import emojis, config

DATA_DIR = (
    os.path.join(Path.home(), ".local/share/Emote")
    if not config.is_flatpak
    else os.path.join(Path.home(), f".var/app/{config.app_id}/data")
)
SHELVE_PATH = os.path.join(DATA_DIR, "user_data")

RECENT_EMOJIS = "recent_emojis"
DEFAULT_RECENT_EMOJIS = ["🙂", "😄", "❤️", "👍", "🤞", "🔥", "🤣", "😍", "😭"]
MAX_RECENT_EMOJIS = 60


# Ensure the data dir exists
os.makedirs(DATA_DIR, exist_ok=True)


def load_recent_emojis():
    with shelve.open(SHELVE_PATH) as db:
        return db.get(RECENT_EMOJIS, DEFAULT_RECENT_EMOJIS)


def update_recent_emojis(char):
    char = emojis.strip_char_skintone(char)
    recent_emojis = load_recent_emojis()

    if char in recent_emojis:
        recent_emojis.remove(char)
        new_recent_emojis = [char] + recent_emojis[: MAX_RECENT_EMOJIS - 2]
    else:
        new_recent_emojis = [char] + recent_emojis[: MAX_RECENT_EMOJIS - 1]

    with shelve.open(SHELVE_PATH) as db:
        db[RECENT_EMOJIS] = new_recent_emojis
