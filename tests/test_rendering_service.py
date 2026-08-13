import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.overlay.rendering_service import RenderingService


class FakeAnimationEngine:
    def __init__(self):
        self.added = []

    def update(self):
        pass

    def add_animation(self, name, extra_data=None):
        self.added.append((name, extra_data))

    def draw(self, x=0, y=0, scale=1.0):
        return {"animation": "idle", "frame": 1, "position": {"x": x, "y": y}, "scale": scale}


class FakePositionTracker:
    def resolve(self, screen_width, screen_height):
        return 10, 20


class FakeWebsocketHandler:
    def __init__(self):
        self.emitted = []

    def emit(self, event, data):
        self.emitted.append((event, data))

    def on_connect(self, callback):
        pass


def _make_service():
    engine = FakeAnimationEngine()
    tracker = FakePositionTracker()
    ws = FakeWebsocketHandler()
    service = RenderingService(
        animation_engine=engine,
        position_tracker=tracker,
        websocket_handler=ws,
    )
    return service, engine, ws


def test_remember_transforms_overlay_text_to_client_format():
    service, _, ws = _make_service()

    service.remember({"action": "overlay_text", "data": {"text": "Hi"}})
    service.render_frame(1920, 1080, scale=1.0)

    _, payload = ws.emitted[-1]
    assert {"type": "overlay_text", "text": "Hi"} in payload["messages"]


def test_remember_transforms_overlay_gif_to_client_format():
    service, _, ws = _make_service()

    service.remember({"action": "overlay_gif", "data": {"gif_id": "wave", "text": "Hey"}})
    service.render_frame(1920, 1080, scale=1.0)

    _, payload = ws.emitted[-1]
    assert {"type": "overlay_gif", "gif_id": "wave", "text": "Hey"} in payload["messages"]


def test_remember_ignores_streampet_messages():
    service, _, ws = _make_service()

    service.remember({"action": "StreamPet", "data": {"animation": "wave"}})
    service.render_frame(1920, 1080, scale=1.0)

    _, payload = ws.emitted[-1]
    assert payload["messages"] == []


def test_remember_keeps_already_client_formatted_messages():
    service, _, ws = _make_service()

    service.remember({"type": "overlay_text", "text": "Direct"})
    service.render_frame(1920, 1080, scale=1.0)

    _, payload = ws.emitted[-1]
    assert {"type": "overlay_text", "text": "Direct"} in payload["messages"]


def test_render_frame_prunes_expired_messages():
    service, _, ws = _make_service()

    service.remember({"action": "overlay_text", "data": {"text": "Old"}}, timestamp=time.time() - 100)
    service.remember({"action": "overlay_text", "data": {"text": "New"}})
    service.render_frame(1920, 1080, scale=1.0)

    _, payload = ws.emitted[-1]
    texts = [m.get("text") for m in payload["messages"] if m.get("type") == "overlay_text"]
    assert "Old" not in texts
    assert "New" in texts


def test_render_frame_emits_stream_pet_data():
    service, _, ws = _make_service()

    service.render_frame(1920, 1080, scale=1.0)

    _, payload = ws.emitted[-1]
    assert payload["stream_pet"]["animation"] == "idle"
