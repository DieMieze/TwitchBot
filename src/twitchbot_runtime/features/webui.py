from __future__ import annotations

from typing import Any

from .base import BaseFeature


class WebUIFeature(BaseFeature):
    """Feature that exposes runtime state and settings through the local UI."""

    def __init__(self, enabled: bool = False) -> None:
        super().__init__(enabled=enabled, name="webui")

    def handles_event(self, event_name: str) -> bool:
        return event_name in {"ui.status", "ui.settings"}

    def handle(self, event_name: str, payload: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
        payload = payload or {}
        if event_name == "ui.settings":
            return [{"type": "webui", "settings": payload.get("settings", {})}]
        return [{"type": "webui", "status": payload.get("status", "running")}]
