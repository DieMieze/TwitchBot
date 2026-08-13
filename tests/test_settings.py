import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest

from twitchbot_runtime.settings import load_settings, save_settings


def test_load_settings_returns_defaults_when_missing(tmp_path):
    settings_path = tmp_path / "settings.json"
    assert not settings_path.exists()

    settings = load_settings(settings_path)

    assert settings["runtime"]["execution_mode"] == "test"
    assert settings["features"] == {}


def test_load_settings_raises_for_non_object_json(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError):
        load_settings(settings_path)


def test_save_settings_persists_and_reload(tmp_path):
    settings_path = tmp_path / "settings.json"
    payload = {"runtime": {"execution_mode": "log_only"}, "features": {"command": {"enabled": True}}}

    saved_path = save_settings(payload, settings_path)

    assert saved_path == settings_path
    assert settings_path.exists()
    assert json.loads(settings_path.read_text(encoding="utf-8")) == payload
