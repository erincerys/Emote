import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
import shelve
import tempfile

from emote import user_data


CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
SETTINGS_PATH = CONFIG_HOME / "emote" / "settings.json"

DEFAULT_THEME = "System Default"
DEFAULT_SHORTCUTS = {
    "focus_search": "<Primary>f",
    "next_category": "<Primary>Tab",
    "previous_category": "<Primary><Shift>Tab",
    "close": "Escape",
}

LEGACY_KEYS = {
    "accelerator": "accelerator_string",
    "theme": "theme",
    "skintone_index": "skintone_index",
    "shown_welcome": "shown_welcome",
}


@dataclass
class Settings:
    accelerator: str = "<Primary><Alt>e"
    theme: str = DEFAULT_THEME
    skintone_index: int = 0
    shown_welcome: bool = False
    auto_paste: bool = True
    window_width: int = 500
    window_height: int = 450
    shortcuts: dict = field(default_factory=lambda: DEFAULT_SHORTCUTS.copy())

    _corrupt = False

    def save(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

        if self._corrupt and SETTINGS_PATH.exists():
            os.replace(SETTINGS_PATH, SETTINGS_PATH.with_suffix(".json.bak"))

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=SETTINGS_PATH.parent,
                prefix=f".{SETTINGS_PATH.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                json.dump(asdict(self), temp_file, indent=2)
                temp_file.write("\n")
            os.replace(temp_path, SETTINGS_PATH)
            self._corrupt = False
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()


def _from_dict(data):
    defaults = Settings()
    field_names = {setting_field.name for setting_field in fields(Settings)}
    values = {key: value for key, value in data.items() if key in field_names}

    for key, value in list(values.items()):
        if type(value) is not type(getattr(defaults, key)):
            del values[key]

    if "shortcuts" in values:
        shortcuts = {
            key: value
            for key, value in values["shortcuts"].items()
            if key in defaults.shortcuts and type(value) is str
        }
        values["shortcuts"] = {**defaults.shortcuts, **shortcuts}

    return Settings(**values)


def _shelve_exists():
    path = Path(user_data.SHELVE_PATH)
    return path.exists() or any(path.parent.glob(f"{path.name}.*"))


def _migrate():
    with shelve.open(str(user_data.SHELVE_PATH), flag="r") as legacy_data:
        values = {
            field_name: legacy_data[legacy_key]
            for field_name, legacy_key in LEGACY_KEYS.items()
            if legacy_key in legacy_data
        }

    migrated = _from_dict(values)
    migrated.save()
    return migrated


def load():
    if not SETTINGS_PATH.exists():
        if _shelve_exists():
            return _migrate()
        return Settings()

    try:
        with SETTINGS_PATH.open(encoding="utf-8") as settings_file:
            data = json.load(settings_file)
        if not isinstance(data, dict):
            raise ValueError("settings must be a JSON object")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        print(f"Warning: could not parse {SETTINGS_PATH}: {error}")
        defaults = Settings()
        defaults._corrupt = True
        return defaults

    return _from_dict(data)
