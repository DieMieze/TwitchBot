from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from twitchbot_runtime.overlay.interfaces import (
    AnimationEngine,
    PositionTracker,
    WebsocketHandler,
)


class OverlayManager:
    """Facade that coordinates overlay actions and the underlying services.

    Track B refactor: the manager now acts as a Facade exposing the
    ``WebsocketHandler``, ``AnimationEngine`` and ``PositionTracker``
    services. The existing dispatch / persistence behaviour is preserved,
    while the backend can be injected or replaced (e.g. in tests) via
    ``_create_backend``.

    The concrete ``Overlay_project.Overlay`` backend is imported lazily so the
    runtime package keeps no hard import-time dependency on Flask / PIL.
    """

    def __init__(
        self,
        store_path: str | Path | None = None,
        backend: Any | None = None,
        websocket_handler: WebsocketHandler | None = None,
        animation_engine: AnimationEngine | None = None,
        position_tracker: PositionTracker | None = None,
        real_backend: bool = False,
        overlay_port: int | None = None,
    ) -> None:
        self.actions: list[dict[str, Any]] = []
        self.store_path = Path(store_path or "output/overlay_actions.jsonl")
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        self._websocket_handler = websocket_handler
        self._animation_engine = animation_engine
        self._position_tracker = position_tracker
        self._real_backend = real_backend
        self._overlay_port = overlay_port

        if backend is not None:
            self.backend = backend
        elif real_backend:
            self.backend = self._create_real_backend(overlay_port)
        else:
            self.backend = self._create_backend()
        if self.backend is not None:
            start = getattr(self.backend, "start", None)
            if callable(start):
                start()

    @staticmethod
    def _create_backend() -> Any:
        """Factory for the concrete overlay backend.

        Returns ``None`` by default so the manager stays usable in lightweight
        (test / headless) contexts without spawning a Flask server. Tests
        monkeypatch this staticmethod to inject a dummy backend.

        Production callers pass ``real_backend=True`` to the manager
        constructor, which routes through :meth:`_create_real_backend`
        instead (so this stub stays inert unless patched).
        """
        return None

    @staticmethod
    def _create_real_backend(overlay_port: int | None = None) -> Any:
        """Factory for the real overlay backend used in production.

        Lazily constructs and returns an :class:`OverlayFacade` instance. The
        facade's constructor does NOT start the Flask server — only
        :meth:`OverlayFacade.start` spawns the multiprocessing subprocess,
        and that is called by the manager after a backend is produced.

        ``overlay_port`` is forwarded to the facade so the subprocess binds
        the configured overlay port instead of the historic default 5000.

        The import is performed inside the method so importing this module
        does not require Flask / PIL to be installed.
        """
        from twitchbot_runtime.overlay.facade import OverlayFacade

        if overlay_port is None:
            return OverlayFacade()
        return OverlayFacade(overlay_port=overlay_port)

    def register_websocket_handler(self, handler: WebsocketHandler) -> None:
        self._websocket_handler = handler

    def register_animation_engine(self, engine: AnimationEngine) -> None:
        self._animation_engine = engine

    def register_position_tracker(self, tracker: PositionTracker) -> None:
        self._position_tracker = tracker

    @property
    def websocket_handler(self) -> WebsocketHandler | None:
        return self._websocket_handler

    @property
    def animation_engine(self) -> AnimationEngine | None:
        return self._animation_engine

    @property
    def position_tracker(self) -> PositionTracker | None:
        return self._position_tracker

    def dispatch(self, action: dict[str, Any]) -> dict[str, Any]:
        """Dispatch an overlay action to the backend and/or services.

        In production (``real_backend=True``) every action is forwarded to the
        real overlay backend (``OverlayFacade``), which drives the browser
        client. The ``StreamPet`` animation is then handled inside the overlay
        subprocess via the ``AnimationEngine``.

        In headless / test contexts (``backend is None``) a registered
        ``AnimationEngine`` is used directly for ``StreamPet`` actions so
        dispatch stays observable without spawning Flask. This second path is
        intentionally inert whenever a backend is present.
        """
        self.actions.append(action)
        with self.store_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(action, ensure_ascii=False) + "\n")

        if self.backend is not None:
            self.backend.send_message(action)
        elif self._animation_engine is not None and action.get("action") == "StreamPet":
            data = action.get("data", {})
            self._animation_engine.add_animation(data.get("animation", "idle"), extra_data=data)

        return action
