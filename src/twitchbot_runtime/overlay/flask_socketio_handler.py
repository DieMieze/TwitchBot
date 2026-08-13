from __future__ import annotations

from collections.abc import Callable
from typing import Any

from twitchbot_runtime.overlay.interfaces import WebsocketHandler


class FlaskSocketIOHandler(WebsocketHandler):
    """Adapter that delegates to the existing Flask-SocketIO server.

    The transport implementation (``flask_socketio.SocketIO``) is not
    rewritten; it is only wrapped behind the ``WebsocketHandler``
    abstraction so callers no longer depend on the concrete library.
    """

    def __init__(self, socketio: Any, app: Any | None = None) -> None:
        self._socketio = socketio
        self._app = app

    def start(self, host: str = "127.0.0.1", port: int = 5000, **kwargs: Any) -> None:
        run_kwargs = {
            "host": host,
            "port": port,
            "debug": kwargs.get("debug", False),
            "use_reloader": kwargs.get("use_reloader", False),
        }
        if self._app is None:
            self._socketio.run(**run_kwargs)
        else:
            self._socketio.run(self._app, **run_kwargs)

    def stop(self) -> None:
        self._socketio.stop()

    def emit(self, event: str, data: dict[str, Any]) -> None:
        self._socketio.emit(event, data)

    def on_connect(self, callback: Callable[..., Any]) -> None:
        self._socketio.on("connect")(callback)
