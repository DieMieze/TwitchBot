import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.reaction_engine import ReactionEngine


def _engine(overlay_calls, streampet_calls=None, counter=None, provider=None):
    sp = streampet_calls if streampet_calls is not None else []
    return ReactionEngine(
        send_chat=lambda broadcaster_id, message: None,
        overlay_dispatch=lambda action: overlay_calls.append(action),
        create_clip=lambda: "",
        counter_handler=counter or (lambda action, payload: None),
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: sp.append(payload),
        speech_bubble_provider=provider,
    )


class _Counter:
    def __init__(self):
        self.calls = []

    def resolve_placeholders(self, message):
        self.calls.append(message)
        return message.replace("{counter:score:current}", "7")

    def __call__(self, action, payload):
        return None


def test_overlay_text_resolves_username_placeholder():
    calls = []
    engine = _engine(calls)
    engine.execute(
        [{"type": "overlay_text", "text": "Hi {username}!"}],
        context={"username": "Bob"},
    )
    assert calls == [{"action": "overlay_text", "data": {"text": "Hi Bob!"}}]


def test_overlay_text_resolves_args_placeholder():
    calls = []
    engine = _engine(calls)
    engine.execute(
        [{"type": "overlay_text", "text": "{args[0]} says {target}"}],
        context={"args": ["world"]},
    )
    assert calls == [{"action": "overlay_text", "data": {"text": "world says world"}}]


def test_overlay_text_resolves_counter_placeholder():
    calls = []
    counter = _Counter()
    engine = _engine(calls, counter=counter)
    engine.execute(
        [{"type": "overlay_text", "text": "Score: {counter:score:current}"}],
        context={},
    )
    assert calls == [{"action": "overlay_text", "data": {"text": "Score: 7"}}]
    assert counter.calls == ["Score: {counter:score:current}"]


def test_overlay_gif_resolves_text_placeholder():
    calls = []
    engine = _engine(calls)
    engine.execute(
        [{"type": "overlay_gif", "gif_id": "dance", "text": "Winner: {username}"}],
        context={"username": "Alice"},
    )
    assert calls == [{"action": "overlay_gif", "data": {"gif_id": "dance", "text": "Winner: Alice"}}]


def test_overlay_text_unresolvable_token_left_intact():
    calls = []
    engine = _engine(calls)
    engine.execute(
        [{"type": "overlay_text", "text": "Hi {unknown_key}"}],
        context={"username": "Bob"},
    )
    assert calls == [{"action": "overlay_text", "data": {"text": "Hi {unknown_key}"}}]


def test_streampet_data_contains_username_and_args():
    calls = []
    sp_calls = []
    engine = _engine(calls, streampet_calls=sp_calls)
    engine.execute(
        [{"type": "streampet", "gif_id": "wave"}],
        context={"event_name": "command", "username": "Bob", "args": ["hi"]},
    )
    assert len(calls) == 1
    assert calls[0]["action"] == "StreamPet"
    data = calls[0]["data"]
    assert data["animation"] == "wave"
    assert data["event"] == "command"
    assert data["username"] == "Bob"
    assert data["args"] == ["hi"]
    assert data["speech_bubble_text"] == ""
    assert data["speech_bubble_toggle"] is False


def test_streampet_data_username_falls_back_to_user_name():
    calls = []
    engine = _engine(calls)
    engine.execute(
        [{"type": "streampet", "gif_id": "wave"}],
        context={"event_name": "follow", "user_name": "Carol"},
    )
    assert calls[0]["data"]["username"] == "Carol"


def test_streampet_speech_bubble_text_resolved_with_placeholders():
    calls = []
    engine = _engine(
        calls,
        provider=lambda: {
            "speech_bubble_text": "Hi {username}, you said {args[0]}",
            "speech_bubble_toggle": True,
        },
    )
    engine.execute(
        [{"type": "streampet", "gif_id": "wave"}],
        context={"event_name": "command", "username": "Bob", "args": ["hello"]},
    )
    data = calls[0]["data"]
    assert data["speech_bubble_text"] == "Hi Bob, you said hello"
    assert data["speech_bubble_toggle"] is True


def test_streampet_speech_bubble_counter_resolved():
    calls = []
    counter = _Counter()
    engine = _engine(
        calls,
        counter=counter,
        provider=lambda: {
            "speech_bubble_text": "Score: {counter:score:current}",
            "speech_bubble_toggle": True,
        },
    )
    engine.execute([{"type": "streampet", "gif_id": "wave"}], context={"username": "X"})
    data = calls[0]["data"]
    assert data["speech_bubble_text"] == "Score: 7"


def test_streampet_provider_returning_none_yields_empty_bubble():
    calls = []
    engine = _engine(calls, provider=lambda: None)
    engine.execute([{"type": "streampet", "gif_id": "wave"}], context={"username": "X"})
    data = calls[0]["data"]
    assert data["speech_bubble_text"] == ""
    assert data["speech_bubble_toggle"] is False


def test_streampet_default_provider_when_not_injected_yields_empty():
    calls = []
    engine = ReactionEngine(
        send_chat=lambda broadcaster_id, message: None,
        overlay_dispatch=lambda action: calls.append(action),
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: None,
    )
    engine.execute([{"type": "streampet", "gif_id": "wave"}], context={"username": "X"})
    data = calls[0]["data"]
    assert data["speech_bubble_text"] == ""
    assert data["speech_bubble_toggle"] is False


def test_streampet_handler_payload_unchanged_shape():
    sp_calls = []
    calls = []
    engine = _engine(calls, streampet_calls=sp_calls)
    engine.execute([{"type": "streampet", "gif_id": "dance"}], context={"event_name": "follow"})
    assert sp_calls == [{"gif_id": "dance", "event": "follow"}]
