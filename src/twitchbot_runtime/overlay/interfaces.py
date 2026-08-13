from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class WebsocketHandler(ABC):
    """Abstraction over the websocket transport (Flask-SocketIO)."""

    @abstractmethod
    def start(self, host: str = "127.0.0.1", port: int = 5000, **kwargs: Any) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def emit(self, event: str, data: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def on_connect(self, callback: Callable[..., Any]) -> None:
        ...


class AnimationEngine(ABC):
    """Abstraction over the animation/GIF engine (StreamPet)."""

    @abstractmethod
    def preload(self) -> None:
        ...

    @abstractmethod
    def add_animation(self, animation_name: str, extra_data: dict[str, Any] | None = None) -> None:
        ...

    @abstractmethod
    def update(self) -> None:
        ...

    @abstractmethod
    def draw(self, x: int = 0, y: int = 0, scale: float = 1.0) -> dict[str, Any] | None:
        ...


class PositionTracker(ABC):
    """Abstraction over overlay element position resolution."""

    @abstractmethod
    def set_position(self, x: int, y: int) -> None:
        ...

    @abstractmethod
    def get_position(self) -> tuple[int, int]:
        ...

    @abstractmethod
    def resolve(self, screen_width: int, screen_height: int) -> tuple[int, int]:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...
