import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.bot import TwitchBot
from twitchbot_runtime.features.overlay import OverlayFeature


def test_twitchbot_handle_event_resolves_command_trigger():
    sent = []
    bot = TwitchBot(
        settings_path=None,
        handlers={
            "send_chat": lambda channel, message: sent.append((channel, message)),
            "overlay_dispatch": lambda action: None,
            "create_clip": lambda: "https://clips.twitch.tv/test",
        },
    )
    bot.settings["triggers"] = [
        {
            "name": "hello_cmd",
            "when": {
                "kind": "and",
                "children": [
                    {"kind": "leaf", "condition": {"type": "command", "command": "!hello"}}
                ],
            },
            "reactions": {
                "kind": "seq",
                "children": [
                    {"kind": "reaction", "reaction": {"type": "chat_reply", "message": "Hi"}}
                ],
            },
        }
    ]
    bot.trigger_resolver.triggers = bot.settings["triggers"]

    reactions = bot.handle_event("chat.message", {"message": "!hello", "channel": "#test"})

    assert reactions == [{"type": "chat_reply", "channel": "#test", "message": "Hi"}]
    assert sent == [("#test", "Hi")]


def test_twitchbot_handle_event_includes_overlay_feature_reaction():
    bot = TwitchBot(
        settings_path=None,
        handlers={
            "send_chat": lambda channel, message: None,
            "overlay_dispatch": lambda action: None,
        },
    )
    bot.feature_manager.register(OverlayFeature(enabled=True))

    reactions = bot.handle_event("event.test", {"message": "Hello"})

    assert reactions == [{"type": "overlay_text", "text": "Hello"}]


def test_twitchbot_handle_event_dispatches_streampet_reaction():
    bot = TwitchBot(
        settings_path=None,
        handlers={
            "send_chat": lambda channel, message: None,
            "overlay_dispatch": lambda action: None,
            "create_clip": lambda: "",
            "streampet_handler": lambda payload: {"gif_id": payload.get("gif_id"), "event": payload.get("event")},
        },
    )
    bot.settings["triggers"] = [
        {
            "name": "sub_pet",
            "when": {
                "kind": "and",
                "children": [{"kind": "leaf", "condition": {"type": "sub"}}],
            },
            "reactions": {
                "kind": "seq",
                "children": [
                    {"kind": "reaction", "reaction": {"type": "streampet", "gif_id": "sub"}}
                ],
            },
        }
    ]
    bot.trigger_resolver.triggers = bot.settings["triggers"]

    reactions = bot.handle_event("event.sub", {"gif_id": "sub"})

    assert reactions == [{"type": "streampet", "result": {"gif_id": "sub", "event": "event.sub"}}]
