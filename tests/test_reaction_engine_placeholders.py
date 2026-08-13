import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.reaction_engine import ReactionEngine


def _engine(calls, moderation_calls=None):
    mod_calls = moderation_calls if moderation_calls is not None else []
    return ReactionEngine(
        send_chat=lambda broadcaster_id, message: calls.append((broadcaster_id, message)),
        overlay_dispatch=lambda action: None,
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: mod_calls.append((action, payload)),
        streampet_handler=lambda payload: None,
    )


def test_chat_reply_resolves_args_placeholder():
    sent = []
    engine = _engine(sent)
    engine.execute(
        [{"type": "chat_reply", "message": "Hello {args[0]}!"}],
        context={"args": ["world"], "channel": "streamer"},
    )

    assert sent == [("streamer", "Hello world!")]


def test_chat_reply_resolves_multiple_args_placeholders():
    sent = []
    engine = _engine(sent)
    engine.execute(
        [{"type": "chat_reply", "message": "{args[0]} {args[1]} {args[2]}"}],
        context={"args": ["a", "b", "c"]},
    )

    assert sent == [("#channel", "a b c")]


def test_chat_reply_args_out_of_range_left_intact():
    sent = []
    engine = _engine(sent)
    engine.execute(
        [{"type": "chat_reply", "message": "{args[5]}"}],
        context={"args": ["only_one"]},
    )

    assert sent == [("#channel", "{args[5]}")]


def test_chat_reply_no_args_in_context_leaves_token_intact():
    sent = []
    engine = _engine(sent)
    engine.execute(
        [{"type": "chat_reply", "message": "{args[0]}"}],
        context={"channel": "streamer"},
    )

    assert sent == [("streamer", "{args[0]}")]


def test_target_placeholder_resolves_to_args0():
    moderation_calls = []
    engine = _engine([], moderation_calls=moderation_calls)
    engine.execute(
        [{"type": "moderation", "action": "ban", "target": "{target}"}],
        context={"args": ["spammer"]},
    )

    assert moderation_calls == [("ban", {"type": "moderation", "action": "ban", "target": "spammer"})]


def test_target_placeholder_left_intact_without_args():
    moderation_calls = []
    engine = _engine([], moderation_calls=moderation_calls)
    engine.execute(
        [{"type": "moderation", "action": "ban", "target": "{target}"}],
        context={},
    )

    assert moderation_calls[0][1]["target"] == "{target}"


def test_moderation_target_resolves_args_index_directly():
    moderation_calls = []
    engine = _engine([], moderation_calls=moderation_calls)
    engine.execute(
        [{"type": "moderation", "action": "timeout", "target": "{args[1]}", "duration": 300}],
        context={"args": ["ignored", "realtarget"]},
    )

    assert moderation_calls[0][1]["target"] == "realtarget"
    assert moderation_calls[0][1]["duration"] == 300


def test_moderation_without_target_passes_empty_string():
    moderation_calls = []
    engine = _engine([], moderation_calls=moderation_calls)
    engine.execute(
        [{"type": "moderation", "action": "ban"}],
        context={"args": ["x"]},
    )

    assert moderation_calls[0][1]["target"] == ""


def test_chat_reply_uses_broadcaster_id_when_present():
    sent = []
    engine = _engine(sent)
    engine.execute(
        [{"type": "chat_reply", "message": "hi"}],
        context={"broadcaster_id": "999", "channel": "streamer"},
    )

    assert sent == [("999", "hi")]


def test_chat_reply_falls_back_to_channel_when_no_broadcaster_id():
    sent = []
    engine = _engine(sent)
    engine.execute(
        [{"type": "chat_reply", "message": "hi", "channel": "#test"}],
        context={"channel": "#test"},
    )

    assert sent == [("#test", "hi")]
