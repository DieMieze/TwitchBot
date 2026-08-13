import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.reaction_engine import ReactionEngine
from twitchbot_runtime.settings import load_settings


def test_load_settings_from_disk(tmp_path):
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {"execution_mode": "bot"},
                "features": {"command": {"enabled": True}},
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings["runtime"]["execution_mode"] == "bot"
    assert settings["features"]["command"]["enabled"] is True


def test_reaction_engine_executes_side_effects():
    calls = []
    engine = ReactionEngine(
        send_chat=lambda channel, message: calls.append(("chat", channel, message)),
        overlay_dispatch=lambda action: calls.append(("overlay", action)),
        create_clip=lambda: "https://clips.twitch.tv/demo",
        counter_handler=lambda action, payload: {"action": action, "payload": payload},
        moderation_handler=lambda action, payload: {"action": action, "payload": payload},
        streampet_handler=lambda payload: {"payload": payload},
    )

    actions = engine.execute(
        [
            {"type": "chat_reply", "message": "Hello", "channel": "#test"},
            {"type": "overlay_text", "text": "Welcome"},
            {"type": "overlay_gif", "gif_id": "welcome", "text": "Hi"},
            {"type": "clip"},
            {"type": "counter", "action": "query", "name": "score"},
            {"type": "moderation", "action": "ban", "target": "spam"},
            {"type": "streampet", "gif_id": "party"},
        ],
        {"channel": "#test"},
    )

    assert calls[0] == ("chat", "#test", "Hello")
    assert calls[1] == ("overlay", {"action": "overlay_text", "data": {"text": "Welcome"}})
    assert calls[2] == ("overlay", {"action": "overlay_gif", "data": {"gif_id": "welcome", "text": "Hi"}})
    assert calls[3] == ("chat", "#test", "Clip erstellt: https://clips.twitch.tv/demo")
    assert [action["type"] for action in actions] == [
        "chat_reply",
        "overlay_text",
        "overlay_gif",
        "clip",
        "counter",
        "moderation",
        "streampet",
    ]
