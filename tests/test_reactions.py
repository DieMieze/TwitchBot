import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.reaction_engine import ReactionEngine


def test_reaction_engine_executes_chat_and_overlay_and_clip():
    calls = []
    engine = ReactionEngine(
        send_chat=lambda channel, message: calls.append(("chat", channel, message)),
        overlay_dispatch=lambda action: calls.append(("overlay", action)),
        create_clip=lambda: "https://clips.twitch.tv/demo",
        counter_handler=lambda action, payload: {"type": "counter", "action": action, "payload": payload},
        moderation_handler=lambda action, payload: {"type": "moderation", "action": action, "payload": payload},
        streampet_handler=lambda payload: {"type": "streampet", "payload": payload},
    )

    actions = engine.execute(
        [
            {"type": "chat_reply", "channel": "#test", "message": "Hello"},
            {"type": "overlay_text", "text": "Welcome"},
            {"type": "overlay_gif", "gif_id": "welcome", "text": "Hi"},
            {"type": "clip"},
        ],
        {"channel": "#test"},
    )

    assert calls[0] == ("chat", "#test", "Hello")
    assert calls[1] == ("overlay", {"action": "overlay_text", "data": {"text": "Welcome"}})
    assert calls[2] == ("overlay", {"action": "overlay_gif", "data": {"gif_id": "welcome", "text": "Hi"}})
    assert calls[3] == ("chat", "#test", "Clip erstellt: https://clips.twitch.tv/demo")
    assert [action["type"] for action in actions] == ["chat_reply", "overlay_text", "overlay_gif", "clip"]


def test_reaction_engine_handles_unknown_reaction_type():
    engine = ReactionEngine(
        send_chat=lambda channel, message: None,
        overlay_dispatch=lambda action: None,
        create_clip=lambda: "",
        counter_handler=lambda action, payload: None,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: None,
    )

    actions = engine.execute([{"type": "unknown_action"}])

    assert len(actions) == 1
    assert actions[0]["type"] == "unknown"
