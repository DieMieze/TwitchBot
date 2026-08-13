from __future__ import annotations

from typing import Any


class FeatureManager:
    """Dispatches events to registered features."""

    def __init__(self) -> None:
        self._features: list[Any] = []

    def register(self, feature: Any) -> None:
        self._features.append(feature)

    def dispatch(self, event_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        result: dict[str, Any] = {}
        for feature in self._features:
            if getattr(feature, "enabled", False) and feature.handles_event(event_name):
                result[feature.name] = feature.handle(event_name, payload)
        return result
