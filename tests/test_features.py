import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.feature_manager import FeatureManager
from twitchbot_runtime.features.moderation import ModerationFeature
from twitchbot_runtime.features.overlay import OverlayFeature
from twitchbot_runtime.features.webui import WebUIFeature

_MODERATION_EVENTS = ("user.ban", "user.timeout", "message.deleted", "message.delete")


def test_feature_manager_dispatch_ignores_disabled_features():
    manager = FeatureManager()
    manager.register(OverlayFeature(enabled=False))

    result = manager.dispatch("event.test", {"message": "Hi"})

    assert result == {}


def test_overlay_feature_handles_event_test():
    feature = OverlayFeature(enabled=True)

    reactions = feature.handle("event.test", {"message": "Hello"})

    assert reactions == [{"type": "overlay_text", "text": "Hello"}]


def test_webui_feature_handles_status_events():
    feature = WebUIFeature(enabled=True)

    reactions = feature.handle("ui.status", {"status": "online"})

    assert reactions == [{"type": "webui", "status": "online"}]


def test_moderation_feature_is_noop_when_enabled():
    feature = ModerationFeature(enabled=True)

    for event_name in _MODERATION_EVENTS:
        assert feature.handle(event_name, {"target": "x"}) is None


def test_moderation_feature_handles_no_event():
    feature = ModerationFeature(enabled=True)

    for event_name in _MODERATION_EVENTS:
        assert feature.handles_event(event_name) is False


def test_moderation_feature_not_in_dispatch_results():
    manager = FeatureManager()
    manager.register(ModerationFeature(enabled=True))

    for event_name in _MODERATION_EVENTS:
        assert manager.dispatch(event_name, {"target": "x"}) == {}
