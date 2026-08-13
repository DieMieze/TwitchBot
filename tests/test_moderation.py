import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.moderation_handler import ModerationHandler


def test_ban_in_production_logs_and_returns_stub():
    handler = ModerationHandler(mode="production")

    result = handler.handle("ban", {"target": "spammer"})

    assert result["status"] == "stub_executed"
    assert result["action"] == "ban"
    assert result["target"] == "spammer"


def test_timeout_extracts_duration():
    handler = ModerationHandler(mode="production")

    result = handler.handle("timeout", {"target": "user", "duration": 300})

    assert result["duration"] == 300


def test_delete_message_extracts_message_id():
    handler = ModerationHandler(mode="production")

    result = handler.handle("delete_message", {"target": "user", "message_id": "msg123"})

    assert result["message_id"] == "msg123"


def test_silent_mode_returns_noop():
    handler = ModerationHandler(mode="silent")

    result = handler.handle("ban", {"target": "x"})

    assert result["status"] == "noop"


def test_test_mode_returns_noop():
    handler = ModerationHandler(mode="test")

    result = handler.handle("ban", {"target": "x"})

    assert result["status"] == "noop"


def test_unknown_action_returns_error():
    handler = ModerationHandler(mode="production")

    result = handler.handle("frobnicate", {})

    assert result["status"] == "unknown_action"


def test_actor_injection_dispatches_ban_in_production():
    class FakeActor:
        def __init__(self):
            self.calls = []

        def ban(self, target, reason=None):
            self.calls.append(("ban", target, reason))
            return {"status": "executed", "action": "ban", "target": target}

        def timeout(self, target, duration, reason=None):
            self.calls.append(("timeout", target, duration, reason))
            return {"status": "executed", "action": "timeout", "target": target}

        def delete_message(self, message_id):
            self.calls.append(("delete_message", message_id))
            return {"status": "executed", "action": "delete_message"}

        def purge(self, target):
            self.calls.append(("purge", target))
            return {"status": "executed", "action": "purge"}

    actor = FakeActor()
    handler = ModerationHandler(mode="production", actor=actor)

    ban_result = handler.handle("ban", {"target": "spammer", "reason": "test"})
    handler.handle("timeout", {"target": "user", "duration": 300})

    assert ban_result["status"] == "executed"
    assert ban_result["target"] == "spammer"
    assert ("ban", "spammer", "test") in actor.calls
    assert ("timeout", "user", 300, None) in actor.calls


def test_actor_not_called_in_silent_mode():
    class RecordingActor:
        def __init__(self):
            self.calls = []

        def ban(self, target, reason=None):
            self.calls.append(("ban", target))
            return {"status": "executed"}

    actor = RecordingActor()
    handler = ModerationHandler(mode="silent", actor=actor)

    result = handler.handle("ban", {"target": "spammer"})

    assert result["status"] == "noop"
    assert actor.calls == []


def test_actor_constructor_backward_compatible_without_actor():
    handler = ModerationHandler(mode="production")

    result = handler.handle("ban", {"target": "spammer"})

    assert result["status"] == "stub_executed"
