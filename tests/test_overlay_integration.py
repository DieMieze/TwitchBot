import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.overlay.manager import OverlayManager
from twitchbot_runtime.reaction_engine import ReactionEngine


class DummyBackend:
    def __init__(self):
        self.messages = []

    def start(self):
        self.started = True

    def send_message(self, message):
        self.messages.append(message)


def test_overlay_manager_forwards_alert_text_and_gif_to_backend(monkeypatch):
    dummy = DummyBackend()

    def factory():
        return dummy

    # _create_backend is a @staticmethod; the replacement must be wrapped the
    # same way so Python does not pass `self`/the class as the first argument.
    monkeypatch.setattr(OverlayManager, "_create_backend", staticmethod(factory))
    manager = OverlayManager()

    manager.dispatch({"action": "overlay_text", "data": {"text": "Hallo"}})
    manager.dispatch({"action": "overlay_gif", "data": {"gif_id": "follow", "text": "Follow"}})

    assert dummy.started is True
    assert dummy.messages[0] == {"action": "overlay_text", "data": {"text": "Hallo"}}
    assert dummy.messages[1] == {"action": "overlay_gif", "data": {"gif_id": "follow", "text": "Follow"}}


def test_reaction_engine_sends_streampet_to_overlay_backend(monkeypatch):
    dummy = DummyBackend()

    def factory():
        return dummy

    # _create_backend is a @staticmethod; wrap the replacement accordingly so
    # the manager does not pass `self` to the factory.
    monkeypatch.setattr(OverlayManager, "_create_backend", staticmethod(factory))
    manager = OverlayManager()
    engine = ReactionEngine(
        send_chat=lambda channel, message: None,
        overlay_dispatch=manager.dispatch,
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: {"payload": payload},
    )

    engine.execute([{"type": "streampet", "gif_id": "party"}], context={"event_name": "event.follow"})

    last = dummy.messages[-1]
    assert last["action"] == "StreamPet"
    assert last["data"]["animation"] == "party"
    assert last["data"]["event"] == "event.follow"


def test_overlay_manager_dispatches_overlay_text_to_backend(monkeypatch):
    dummy = DummyBackend()

    def factory():
        return dummy

    monkeypatch.setattr(OverlayManager, "_create_backend", staticmethod(factory))
    manager = OverlayManager()

    manager.dispatch({"action": "overlay_text", "data": {"text": "Hi"}})

    assert dummy.started is True
    assert {"action": "overlay_text", "data": {"text": "Hi"}} in dummy.messages


def test_overlay_manager_dispatches_overlay_gif_to_backend(monkeypatch):
    dummy = DummyBackend()

    def factory():
        return dummy

    monkeypatch.setattr(OverlayManager, "_create_backend", staticmethod(factory))
    manager = OverlayManager()

    manager.dispatch({"action": "overlay_gif", "data": {"gif_id": "follow", "text": "Follow"}})

    assert dummy.started is True
    assert {"action": "overlay_gif", "data": {"gif_id": "follow", "text": "Follow"}} in dummy.messages


def test_reaction_engine_overlay_text_dispatches_to_overlay(monkeypatch):
    dummy = DummyBackend()

    def factory():
        return dummy

    monkeypatch.setattr(OverlayManager, "_create_backend", staticmethod(factory))
    manager = OverlayManager()
    engine = ReactionEngine(
        send_chat=lambda channel, message: None,
        overlay_dispatch=manager.dispatch,
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: {"payload": payload},
    )

    engine.execute([{"type": "overlay_text", "text": "Hello"}], context={"event_name": "chat.message"})

    assert {"action": "overlay_text", "data": {"text": "Hello"}} in dummy.messages


def test_overlay_manager_real_backend_false_does_not_start_server():
    # Default real_backend=False must keep backend None without spawning a
    # Flask/SocketIO process, so test contexts stay side-effect free.
    manager = OverlayManager()
    assert manager.backend is None


def test_overlay_manager_headless_streampet_path_uses_animation_engine():
    class FakeAnimationEngine:
        def __init__(self):
            self.added = []

        def add_animation(self, name, extra_data=None):
            self.added.append((name, extra_data))

    engine = FakeAnimationEngine()
    manager = OverlayManager(backend=None, animation_engine=engine)

    manager.dispatch({"action": "StreamPet", "data": {"animation": "wave"}})

    assert engine.added == [("wave", {"animation": "wave"})]


def test_overlay_manager_streampet_headless_skipped_when_backend_present(monkeypatch):
    class FakeAnimationEngine:
        def __init__(self):
            self.added = []

        def add_animation(self, name, extra_data=None):
            self.added.append((name, extra_data))

    dummy = DummyBackend()
    engine = FakeAnimationEngine()
    manager = OverlayManager(backend=dummy, animation_engine=engine)

    manager.dispatch({"action": "StreamPet", "data": {"animation": "wave"}})

    assert engine.added == []
    assert {"action": "StreamPet", "data": {"animation": "wave"}} in dummy.messages
