from __future__ import annotations

import time
from typing import Any

from twitchbot_runtime.overlay.interfaces import AnimationEngine, PositionTracker, WebsocketHandler


class RenderingService:
    """Encapsulates the per-frame rendering loop previously inlined in
    ``Overlay._run_overlay``.

    This is the first service extracted in the Track B refactor. It composes
    the ``AnimationEngine``, ``PositionTracker`` and ``WebsocketHandler``
    abstractions so the loop no longer reaches into the concrete ``StreamPet``
    or ``flask_socketio`` implementations directly.
    """

    def __init__(
        self,
        animation_engine: AnimationEngine,
        position_tracker: PositionTracker,
        websocket_handler: WebsocketHandler,
        logger: Any | None = None,
        fps: int = 60,
    ) -> None:
        self._animation_engine = animation_engine
        self._position_tracker = position_tracker
        self._websocket_handler = websocket_handler
        self._logger = logger
        self._fps = fps
        self._delay = 1.0 / fps
        self._messages: list[tuple[Any, float]] = []

    @property
    def messages(self) -> list[tuple[Any, float]]:
        return self._messages

    def remember(self, message: Any, timestamp: float | None = None) -> None:
        transformed = self._transform(message)
        if transformed is None:
            return
        self._messages.append((transformed, timestamp if timestamp is not None else time.time()))

    def _transform(self, message: Any) -> Any:
        """Normalize a queue message into the client-rendered format.

        The reaction engine and overlay manager emit raw payloads shaped as
        ``{"action": <type>, "data": {...}}``. The browser client
        (``overlay.js``) renders frames whose messages carry a ``type`` field
        (``overlay_text`` / ``overlay_gif``). Messages that are already in the
        client format (or are not overlay-text/gif actions) are stored as-is;
        ``None`` is returned for messages that should not be appended to the
        text overlay list (e.g. StreamPet animations handled via the
        animation engine).
        """
        if not isinstance(message, dict):
            return message

        if "type" in message and "action" not in message:
            return message

        action = message.get("action")
        data = message.get("data") or {}

        if action == "overlay_text":
            return {"type": "overlay_text", "text": data.get("text", "")}
        if action == "overlay_gif":
            return {
                "type": "overlay_gif",
                "gif_id": data.get("gif_id", ""),
                "text": data.get("text", ""),
            }
        return None

    def _prune_messages(self, current_time: float, ttl: float = 5.0) -> None:
        self._messages = [m for m in self._messages if current_time - m[1] <= ttl]

    def render_frame(self, screen_width: int, screen_height: int, scale: float = 1.0) -> dict[str, Any] | None:
        self._animation_engine.update()
        x, y = self._position_tracker.resolve(screen_width, screen_height)
        stream_pet_data = self._animation_engine.draw(x, y, scale=scale)

        current_time = time.time()
        self._prune_messages(current_time)
        payload = {
            "stream_pet": stream_pet_data,
            "messages": [m[0] for m in self._messages],
        }
        self._websocket_handler.emit("update", payload)
        return payload

    def frame_delay(self) -> float:
        return self._delay
