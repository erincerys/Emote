import importlib
import json
import shelve

import pytest

from emote import settings as settings_module
from emote import user_data


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    path = config_home / "emote" / "settings.json"
    importlib.reload(settings_module)
    assert settings_module.SETTINGS_PATH == path
    monkeypatch.setattr(user_data, "SHELVE_PATH", str(tmp_path / "missing-shelve"))
    return path


def test_defaults_when_file_is_absent(settings_path):
    assert settings_module.load() == settings_module.Settings()
    assert not settings_path.exists()


def test_round_trip(settings_path):
    expected = settings_module.Settings(
        accelerator="<Primary>space",
        theme="Adwaita-dark",
        skintone_index=3,
        shown_welcome=True,
        auto_paste=False,
        window_width=640,
        window_height=480,
        shortcuts={
            "focus_search": "slash",
            "next_category": "Page_Down",
            "previous_category": "Page_Up",
            "close": "q",
        },
    )

    expected.save()

    assert settings_module.load() == expected
    assert settings_path.read_text().endswith("\n")


def test_unknown_keys_are_ignored(settings_path):
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"theme": "Adwaita", "future": "value"}))

    loaded = settings_module.load()

    assert loaded.theme == "Adwaita"
    assert not hasattr(loaded, "future")


def test_wrong_types_fall_back_to_defaults(settings_path):
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "accelerator": 1,
                "theme": False,
                "skintone_index": "3",
                "shown_welcome": 1,
                "auto_paste": "yes",
                "window_width": True,
                "window_height": 450.0,
                "shortcuts": [],
            }
        )
    )

    assert settings_module.load() == settings_module.Settings()


def test_partial_shortcuts_are_merged_with_defaults(settings_path):
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"shortcuts": {"close": "q", "focus_search": 1, "unknown": "x"}})
    )

    loaded = settings_module.load()

    assert loaded.shortcuts == {**settings_module.DEFAULT_SHORTCUTS, "close": "q"}


def test_corrupt_file_is_backed_up_on_save(settings_path, capsys):
    corrupt_contents = "{not json\n"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(corrupt_contents)

    loaded = settings_module.load()

    assert loaded == settings_module.Settings()
    assert loaded._corrupt
    assert "Warning: could not parse" in capsys.readouterr().out

    loaded.theme = "Adwaita"
    loaded.save()

    assert settings_path.with_suffix(".json.bak").read_text() == corrupt_contents
    assert json.loads(settings_path.read_text())["theme"] == "Adwaita"
    assert not loaded._corrupt


def test_migrates_legacy_shelve(settings_path, tmp_path, monkeypatch):
    shelve_path = tmp_path / "user_data"
    with shelve.open(str(shelve_path)) as legacy_data:
        legacy_data["accelerator_string"] = "<Primary><Alt>x"
        legacy_data["accelerator_label"] = "Ctrl+Alt+X"
        legacy_data["theme"] = "Yaru-dark"
        legacy_data["skintone_index"] = 4
        legacy_data["shown_welcome"] = True
        legacy_data["recent_emojis"] = ["🧪"]
    monkeypatch.setattr(user_data, "SHELVE_PATH", str(shelve_path))

    loaded = settings_module.load()

    assert loaded.accelerator == "<Primary><Alt>x"
    assert loaded.theme == "Yaru-dark"
    assert loaded.skintone_index == 4
    assert loaded.shown_welcome is True
    assert loaded.auto_paste is True
    assert settings_path.exists()
    with shelve.open(str(shelve_path), flag="r") as legacy_data:
        assert legacy_data["recent_emojis"] == ["🧪"]
