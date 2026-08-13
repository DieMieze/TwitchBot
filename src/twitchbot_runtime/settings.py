from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_settings(path: str | Path | None = None) -> dict[str, Any]:
    """Load settings from disk or return a default structure."""
    config_path = Path(path or "settings.json")
    if not config_path.exists():
        return {
            "runtime": {
                "execution_mode": "test",
                "webhook": {"host": "127.0.0.1", "port": 5002},
            },
            "twitch": {"webhook_secret": ""},
            "features": {},
            "triggers": [],
        }

    with config_path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("Settings must be a JSON object")
    return data


def save_settings(settings: dict[str, Any], path: str | Path | None = None) -> Path:
    """Persist settings to disk."""
    config_path = Path(path or "settings.json")
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)
    return config_path
