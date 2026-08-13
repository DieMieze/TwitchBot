import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.overlay.flask_socketio_handler import FlaskSocketIOHandler


class FakeSocketIO:
    def __init__(self):
        self.emitted = []
        self.connect_callbacks = []
        self.stopped = False
        self.run_calls = []

    def emit(self, event, data):
        self.emitted.append((event, data))

    def on(self, event):
        def decorator(func):
            self.connect_callbacks.append((event, func))
            return func
        return decorator

    def stop(self):
        self.stopped = True

    def run(self, app=None, **kwargs):
        self.run_calls.append({"app": app, **kwargs})


class FakeApp:
    pass


def test_emit_delegates_to_socketio():
    socketio = FakeSocketIO()
    handler = FlaskSocketIOHandler(socketio)

    handler.emit("update", {"frame": 1})

    assert socketio.emitted == [("update", {"frame": 1})]


def test_on_connect_registers_callback():
    socketio = FakeSocketIO()
    handler = FlaskSocketIOHandler(socketio)

    callback = lambda: None
    handler.on_connect(callback)

    assert socketio.connect_callbacks[0][0] == "connect"
    assert socketio.connect_callbacks[0][1] is callback


def test_start_passes_host_port_and_run_kwargs():
    socketio = FakeSocketIO()
    app = FakeApp()
    handler = FlaskSocketIOHandler(socketio, app=app)

    handler.start(host="0.0.0.0", port=5050, debug=True, use_reloader=False)

    call = socketio.run_calls[0]
    assert call["app"] is app
    assert call["host"] == "0.0.0.0"
    assert call["port"] == 5050
    assert call["debug"] is True
    assert call["use_reloader"] is False


def test_start_without_app_runs_socketio_directly():
    socketio = FakeSocketIO()
    handler = FlaskSocketIOHandler(socketio)

    handler.start(host="127.0.0.1", port=5000)

    call = socketio.run_calls[0]
    assert call["app"] is None
    assert call["port"] == 5000


def test_stop_delegates_to_socketio():
    socketio = FakeSocketIO()
    handler = FlaskSocketIOHandler(socketio)

    handler.stop()

    assert socketio.stopped is True
