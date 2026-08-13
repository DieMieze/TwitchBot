from __future__ import annotations

from typing import Any

from twitchbot_runtime.overlay.interfaces import AnimationEngine


class StreamPetAnimationEngine(AnimationEngine):
    """Adapter that exposes the existing ``Overlay_project.StreamPet`` class
    behind the ``AnimationEngine`` abstraction.

    The GIF processing logic (preloading, frame advancement, serialization)
    remains inside ``StreamPet`` and is not rewritten; this adapter only
    forwards calls so downstream code depends on the abstraction.
    """

    def __init__(self, stream_pet: Any) -> None:
        self._stream_pet = stream_pet

    def preload(self) -> None:
        preload = getattr(self._stream_pet, "preload_animations", None)
        if callable(preload):
            preload()

    def add_animation(self, animation_name: str, extra_data: dict[str, Any] | None = None) -> None:
        self._stream_pet.add_animation(animation_name, extra_data=extra_data)

    def update(self) -> None:
        self._stream_pet.update()

    def draw(self, x: int = 0, y: int = 0, scale: float = 1.0) -> dict[str, Any] | None:
        return self._stream_pet.draw(x, y, scale=scale)
