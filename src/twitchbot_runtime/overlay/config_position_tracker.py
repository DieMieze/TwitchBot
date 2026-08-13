from __future__ import annotations

from typing import Any

from twitchbot_runtime.overlay.interfaces import PositionTracker


class ConfigPositionTracker(PositionTracker):
    """Tracks element positions based on the overlay config.

    The previous implementation read ``config["stream_pet_config"]["position"]``
    inline inside the update loop. That logic is now encapsulated behind the
    ``PositionTracker`` abstraction while keeping the exact resolution rules.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._position: tuple[int, int] = (0, 0)

    def set_position(self, x: int, y: int) -> None:
        self._position = (int(x), int(y))

    def get_position(self) -> tuple[int, int]:
        return self._position

    def resolve(self, screen_width: int, screen_height: int) -> tuple[int, int]:
        stream_pet_config = self._config.get("stream_pet_config", {})
        position = stream_pet_config.get("position", {"x": 0, "y": 0})
        x = int(position.get("x", 0) * screen_width)
        y = int(position.get("y", 0) * screen_height)
        self._position = (x, y)
        return self._position

    def clear(self) -> None:
        self._position = (0, 0)
