import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.reaction_engine import ReactionEngine


def test_reaction_engine_uses_default_channel_for_chat_reply():
    calls = []
    engine = ReactionEngine(
        send_chat=lambda channel, message: calls.append((channel, message)),
        overlay_dispatch=lambda action: None,
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: None,
    )

    actions = engine.execute([{"type": "chat_reply", "message": "Hello"}])

    assert calls == [("#channel", "Hello")]
    assert actions == [{"type": "chat_reply", "channel": "#channel", "message": "Hello"}]


def test_reaction_engine_overlay_gif_defaults_gif_id_when_missing():
    calls = []
    engine = ReactionEngine(
        send_chat=lambda channel, message: None,
        overlay_dispatch=lambda action: calls.append(action),
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: None,
    )

    actions = engine.execute([{"type": "overlay_gif", "text": "Hey"}])

    assert calls == [{"action": "overlay_gif", "data": {"gif_id": "default", "text": "Hey"}}]
    assert actions == [{"type": "overlay_gif", "gif_id": "default", "text": "Hey"}]


def test_reaction_engine_clip_returns_error_if_no_clip_created():
    engine = ReactionEngine(
        send_chat=lambda channel, message: None,
        overlay_dispatch=lambda action: None,
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: None,
    )

    actions = engine.execute([{"type": "clip"}])

    assert actions == [{"type": "clip", "error": "no_clip_created"}]


def test_reaction_engine_counter_middleware_returns_result():
    engine = ReactionEngine(
        send_chat=lambda channel, message: None,
        overlay_dispatch=lambda action: None,
        create_clip=lambda: "",
        counter_handler=lambda action, payload: {"action": action, "payload": payload},
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: None,
    )

    actions = engine.execute([{"type": "counter", "action": "increment", "name": "score"}])

    assert actions == [{"type": "counter", "result": {"action": "increment", "payload": {"type": "counter", "action": "increment", "name": "score", "category": "default"}}}]


def test_reaction_engine_moderation_middleware_returns_result():
    engine = ReactionEngine(
        send_chat=lambda channel, message: None,
        overlay_dispatch=lambda action: None,
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: {"status": "executed", "payload": payload},
        streampet_handler=lambda payload: None,
    )

    actions = engine.execute([{"type": "moderation", "action": "ban", "target": "spammer"}])

    assert actions == [{"type": "moderation", "result": {"status": "executed", "payload": {"type": "moderation", "action": "ban", "target": "spammer"}}}]


def test_reaction_engine_streampet_uses_context_event_name():
    engine = ReactionEngine(
        send_chat=lambda channel, message: None,
        overlay_dispatch=lambda action: None,
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: {"payload": payload},
    )

    actions = engine.execute([{"type": "streampet"}], context={"event_name": "event.follow"})

    assert actions == [{"type": "streampet", "result": {"payload": {"gif_id": "idle", "event": "event.follow"}}}]


def test_reaction_engine_ignores_none_reactions():
    engine = ReactionEngine(
        send_chat=lambda channel, message: None,
        overlay_dispatch=lambda action: None,
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: None,
    )

    actions = engine.execute([None, {"type": "unknown"}])

    assert actions == [{"type": "unknown", "reaction": {"type": "unknown"}}]
