from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from functools import partial
from multiprocessing import Event as _mp_event
from multiprocessing import Process
from multiprocessing import Queue as _mp_queue

# multiprocessing.Event/Queue are factory functions, not types, so they cannot
# be used directly in type annotations. The concrete classes live in the
# ``multiprocessing.synchronize`` / ``multiprocessing.queues`` submodules.
from multiprocessing.queues import Queue as MpQueue
from multiprocessing.synchronize import Event as MpEvent
from threading import Thread
from typing import Any

from twitchbot_runtime.logger import Logger, get_logger
from twitchbot_runtime.overlay.interfaces import (
    AnimationEngine,
    PositionTracker,
    WebsocketHandler,
)
from twitchbot_runtime.overlay.rendering_service import RenderingService


def _default_log_dir() -> str:
    """Bestimme ein CWD-unabhängiges Log-Verzeichnis.

    Reihenfolge:
    1. Umgebungsvariable ``OVERLAY_LOG_DIR`` (expliziter Override).
    2. Verzeichnis neben ``Stream_Pet.json`` (Projekt-Root) — passt zu
       Windows-Entwicklung und normalem Linux-Deployment.
    3. User-Log-Verzeichnis (``tempfile.gettempdir()``) als letzter Fallback
       für schreibgeschütztes CWD (Linux-System-Service).
    """
    env_dir = os.environ.get("OVERLAY_LOG_DIR")
    if env_dir:
        return env_dir
    try:
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
    except Exception:
        import tempfile
        return tempfile.gettempdir()


def _configure_logger(*, attach_console: bool = False, log_dir: str | None = None) -> Logger:
    stdlib_logger = logging.getLogger("Overlay")
    stdlib_logger.setLevel(logging.DEBUG)
    if not stdlib_logger.hasHandlers():
        # CWD-unabhängiger Log-Pfad: kein relatives "overlay.log" mehr, das bei
        # schreibgeschütztem CWD (Linux-System-Service) crasht.
        target_dir = log_dir if log_dir is not None else _default_log_dir()
        log_path = os.path.join(target_dir, "overlay.log")
        try:
            file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        except (OSError, PermissionError):
            # Fallback auf temporäres Verzeichnis, wenn das Ziel nicht schreibbar ist.
            import tempfile
            log_path = os.path.join(tempfile.gettempdir(), "overlay.log")
            file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        stdlib_logger.addHandler(file_handler)
        if attach_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            stdlib_logger.addHandler(console_handler)
    return get_logger("Overlay")


class OverlayFacade:
    """Facade that exposes the overlay backend behind service abstractions.

    The heavy lifting (multiprocessing subprocess, Flask-SocketIO server,
    ``StreamPet`` GIF handling) is driven from :meth:`_run_overlay`. This
    facade:

    * injects the abstractions (``WebsocketHandler``, ``AnimationEngine``,
      ``PositionTracker``) into the rendering loop,
    * exposes them as properties for external consumers / tests,
    * delegates ``start``/``stop``/``send_message`` to the backend.

    Imports of the concrete ``Overlay_project`` backend are performed lazily
    inside methods so importing this module does not require Flask / PIL.
    """

    def __init__(
        self,
        queue: MpQueue[Any] | None = None,
        running_event: MpEvent | None = None,
        websocket_handler: WebsocketHandler | None = None,
        animation_engine: AnimationEngine | None = None,
        position_tracker: PositionTracker | None = None,
        config_path: str | os.PathLike[str] | None = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
        overlay_port: int = 5000,
    ) -> None:
        self.queue = queue if queue is not None else _mp_queue()
        self.running_event = running_event if running_event is not None else _mp_event()
        self.running_event.clear()
        self.overlay_logger = _configure_logger(attach_console=True)
        self.process: Process | None = None

        self._websocket_handler = websocket_handler
        self._animation_engine = animation_engine
        self._position_tracker = position_tracker
        self._config_path = config_path
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._overlay_port = int(overlay_port)

        import atexit
        atexit.register(self.stop)

    @property
    def websocket_handler(self) -> WebsocketHandler | None:
        return self._websocket_handler

    @property
    def animation_engine(self) -> AnimationEngine | None:
        return self._animation_engine

    @property
    def position_tracker(self) -> PositionTracker | None:
        return self._position_tracker

    def register_websocket_handler(self, handler: WebsocketHandler) -> None:
        self._websocket_handler = handler

    def register_animation_engine(self, engine: AnimationEngine) -> None:
        self._animation_engine = engine

    def register_position_tracker(self, tracker: PositionTracker) -> None:
        self._position_tracker = tracker

    def start(self) -> None:
        if not self.running_event.is_set():
            self.running_event.set()
        if self.process is None or not self.process.is_alive():
            self.process = Process(
                target=self._run_overlay,
                args=(self.queue, self.running_event, self._overlay_port),
            )
            self.process.start()

    # Stop-Strategie (plattformneutral, primärer Pfad):
    #   1. running_event.clear() — sichtbar im Kindprozess (multiprocessing.Event,
    #      Shared-Memory); die innere Drain-Schleife und der update_loop brechen
    #      ab, sobald sie das Flag prüfen.
    #   2. queue.put_nowait("STOP") — Trigger, damit der blockierende
    #      websocket_handler.start()-Aufruf im Kindprozess via socketio.stop()
    #      zurückkehrt (SocketIO-Loop).
    #   3. process.join(timeout) — wartet auf sauberes Beenden.
    #   4. process.terminate() — Notbremse nur nach Timeout. Plattform-Delta:
    #      POSIX = SIGTERM (Kindprozess-Signalhandler aus _run_overlay läuft,
    #      kann sauber aufräumen), Windows = TerminateProcess (Harter Kill, kein
    #      Handler). Da der primäre Stoppfad (1+2) plattformneutral ist, ist
    #      terminate() hier nur Verteidigung in der Tiefe.
    # Kein os.kill/SIGTERM von außen: unter Windows unzuverlässig und wird vom
    # Kindprozess nicht als Signalhandler ausgelöst.
    _JOIN_TIMEOUT_SECONDS = 5

    def stop(self) -> None:
        if self.process and self.process.is_alive():
            self.overlay_logger.info("Sende 'STOP' an den Overlay-Prozess.")
            self.running_event.clear()          # sofort signalisieren (primär, vor join)
            try:
                self.queue.put_nowait("STOP")   # non-blocking, Trigger für socketio.stop()
            except Exception:
                pass
            self.process.join(timeout=self._JOIN_TIMEOUT_SECONDS)
            if self.process.is_alive():
                self.overlay_logger.warning(
                    f"Overlay-Prozess nach {self._JOIN_TIMEOUT_SECONDS}s nicht beendet; terminate() als Notbremse."
                )
                self.process.terminate()
                self.process.join(timeout=self._JOIN_TIMEOUT_SECONDS)
                if self.process.is_alive():
                    self.overlay_logger.error("Overlay-Prozess konnte auch nach terminate() nicht beendet werden.")
            self.overlay_logger.info("Overlay-Prozess wurde gestoppt.")
        self.running_event.clear()

    def send_message(self, message: Any) -> None:
        if self.process and self.process.is_alive():
            self.queue.put(message)

    def _load_config(self) -> dict[str, Any]:
        config_path = self._config_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "Stream_Pet.json"
        )
        config_path = os.path.abspath(config_path)
        try:
            with open(config_path, encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError) as exc:
            # Kein harter Subprocess-Crash mehr bei fehlender/korrupter
            # Stream_Pet.json: leere Config, StreamPet idle-fallback greift.
            self.overlay_logger.error(f"Fehler beim Laden von {config_path}: {exc}")
            return {}

    def _build_default_services(self, config: dict[str, Any]) -> tuple[
        AnimationEngine, PositionTracker, WebsocketHandler
    ]:
        if self._position_tracker is None:
            from twitchbot_runtime.overlay.config_position_tracker import ConfigPositionTracker
            position_tracker: PositionTracker = ConfigPositionTracker(config)
        else:
            position_tracker = self._position_tracker

        if self._animation_engine is None:
            from Overlay_project.StreamPet import StreamPet
            stream_pet = StreamPet(
                idle_gif_path=config.get("idle"),
                animations=config.get("animations", {}),
                overlay_logger=self.overlay_logger,
                scale=self._screen_width / 1920,
            )
            from twitchbot_runtime.overlay.streampet_animation_engine import StreamPetAnimationEngine
            animation_engine: AnimationEngine = StreamPetAnimationEngine(stream_pet)
        else:
            animation_engine = self._animation_engine

        if self._websocket_handler is None:
            from Overlay_project.overlay_server import app, socketio
            from twitchbot_runtime.overlay.flask_socketio_handler import FlaskSocketIOHandler
            websocket_handler: WebsocketHandler = FlaskSocketIOHandler(socketio, app)
        else:
            websocket_handler = self._websocket_handler

        return animation_engine, position_tracker, websocket_handler

    def _run_overlay(self, queue: MpQueue[Any], running_event: MpEvent, overlay_port: int = 5000) -> None:
        from Overlay_project.overlay_helpers import handle_signals, open_browser_when_ready

        overlay_logger = _configure_logger()
        websocket_handler: WebsocketHandler | None = None

        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            overlay_logger.info("Overlay-Prozess gestartet.")
            overlay_logger.info(f"Prozess-ID: {os.getpid()}")
            overlay_logger.info(f"Overlay-Port: {overlay_port}")

            overlay_url = f"http://127.0.0.1:{overlay_port}/"
            Thread(target=open_browser_when_ready, args=(overlay_url,)).start()

            config = self._load_config()
            animation_engine, position_tracker, websocket_handler = self._build_default_services(config)

            signal.signal(signal.SIGTERM, partial(handle_signals, overlay_logger, running_event, websocket_handler))
            signal.signal(signal.SIGINT, partial(handle_signals, overlay_logger, running_event, websocket_handler))

            websocket_handler.on_connect(lambda: overlay_logger.info("Client connected"))

            rendering_service = RenderingService(
                animation_engine=animation_engine,
                position_tracker=position_tracker,
                websocket_handler=websocket_handler,
                logger=overlay_logger,
            )

            screen_width = self._screen_width
            screen_height = self._screen_height
            scale = screen_width / 1920

            def update_loop() -> None:
                while running_event.is_set():
                    try:
                        while not queue.empty():
                            if not running_event.is_set():          # Backlog sofort verwerfen
                                websocket_handler.stop()
                                break
                            overlay_logger.debug("Nachrichten aus der Queue verarbeiten...")
                            try:
                                message = queue.get()
                            except Exception:
                                overlay_logger.error("Fehler: Queue war leer während des Zugriffs.")
                                continue
                            overlay_logger.debug(f"Nachricht aus der Queue erhalten: {message}")
                            if message == "STOP":
                                print("Nachricht 'STOP' erhalten. Beende den Overlay-Prozess.")
                                running_event.clear()
                                websocket_handler.stop()
                                break
                            elif isinstance(message, dict) and message.get("action") == "StreamPet":
                                animation = message.get("data", {}).get("animation", "idle")
                                animation_engine.add_animation(animation, extra_data=message.get("data", {}))
                            elif isinstance(message, dict) and message.get("action") == "overlay_text":
                                overlay_logger.info(f"overlay_text: {message.get('data', {}).get('text', '')}")
                            elif isinstance(message, dict) and message.get("action") == "overlay_gif":
                                overlay_logger.info(f"overlay_gif: {message.get('data', {}).get('gif_id')}")
                            else:
                                overlay_logger.warning(f"Unbekannte Nachricht erhalten: {message}")
                            rendering_service.remember(message)
                    except Exception as exc:
                        overlay_logger.error(f"Fehler im Overlay: {exc}")

                    rendering_service.render_frame(screen_width, screen_height, scale=scale)
                    time.sleep(rendering_service.frame_delay())

                if not running_event.is_set():
                    print("Overlay-Prozess wird beendet.")

            Thread(target=update_loop).start()
            websocket_handler.start(host="127.0.0.1", port=overlay_port, debug=False, use_reloader=False)

        except Exception as exc:
            overlay_logger.error(f"Fehler im Overlay-Prozess: {exc}")
        finally:
            # Kontrolliertes Aufräumen, kein abrupter sys.exit(). Der Subprozess
            # endet von selbst, sobald websocket_handler.start() zurückkehrt
            # (STOP-Pfad via running_event/queue → socketio.stop()).
            if websocket_handler is not None:
                try:
                    websocket_handler.stop()
                except Exception:
                    pass
            overlay_logger.info("Overlay-Prozess beendet.")
