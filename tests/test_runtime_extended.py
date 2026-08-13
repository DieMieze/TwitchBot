import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.bot import TwitchBot
from twitchbot_runtime.overlay.manager import OverlayManager


def _leaf(condition):
    return {"kind": "leaf", "condition": condition}


def _and(*leaves):
    return {"kind": "and", "children": list(leaves)}


def _reaction(type_, **fields):
    base = {"type": type_}
    base.update(fields)
    return {"kind": "reaction", "reaction": base}


def _seq(*reactions):
    return {"kind": "seq", "children": list(reactions)}


def test_twitchbot_resolves_timer_trigger_from_settings():
    bot = TwitchBot(settings_path=None, handlers={"send_chat": lambda channel, message: None})
    bot.settings["triggers"] = [
        {
            "name": "timer_ping",
            "event": "timer.tick",
            "when": _and(
                _leaf({"type": "compare", "field": "{event_name}", "op": "==", "value": "timer.tick"})
            ),
            "reactions": _seq(_reaction("chat_reply", message="tick")),
        }
    ]

    actions = bot.handle_event("timer.tick", {"trigger_name": "timer_ping"})

    assert actions == [{"type": "chat_reply", "channel": "#channel", "message": "tick"}]


def test_twitchbot_resolves_all_and_any_conditions():
    bot = TwitchBot(settings_path=None, handlers={"send_chat": lambda channel, message: None})
    bot.settings["triggers"] = [
        {
            "name": "combo",
            "event": "chat.message",
            "when": _and(
                _leaf({"type": "compare", "field": "{message}", "op": "==", "value": "hello"}),
                {
                    "kind": "or",
                    "children": [
                        _leaf({"type": "compare", "field": "{channel}", "op": "==", "value": "#test"}),
                        _leaf({"type": "compare", "field": "{channel}", "op": "==", "value": "#other"}),
                    ],
                },
            ),
            "reactions": _seq(_reaction("chat_reply", message="ok")),
        }
    ]

    actions = bot.handle_event("chat.message", {"message": "hello", "channel": "#test"})

    assert actions == [{"type": "chat_reply", "channel": "#test", "message": "ok"}]


def test_twitchbot_handles_moderation_reactions():
    bot = TwitchBot(
        settings_path=None,
        handlers={
            "send_chat": lambda channel, message: None,
            "moderation_handler": lambda action, payload: {"action": action, "payload": payload},
        },
    )
    bot.settings["triggers"] = [
        {
            "name": "timeout_on_event",
            "event": "user.timeout",
            "when": _and(
                _leaf({"type": "compare", "field": "{event_name}", "op": "==", "value": "user.timeout"})
            ),
            "reactions": _seq(_reaction("moderation", action="timeout", target="spammer", duration=60)),
        }
    ]
    bot.trigger_resolver.triggers = bot.settings["triggers"]

    actions = bot.handle_event("user.timeout", {"target": "spammer", "duration": 60})

    assert actions == [{"type": "moderation", "result": {"action": "timeout", "payload": {"type": "moderation", "action": "timeout", "target": "spammer", "duration": 60}}}]


def test_overlay_manager_dispatch_records_actions():
    manager = OverlayManager()

    result = manager.dispatch({"action": "overlay_text", "data": {"text": "Hello"}})

    assert result == {"action": "overlay_text", "data": {"text": "Hello"}}
    assert manager.actions[-1] == result


def test_twitchbot_resolves_command_condition_trigger():
    bot = TwitchBot(settings_path=None, handlers={"send_chat": lambda channel, message: None})
    bot.settings["triggers"] = [
        {
            "name": "hello_cmd",
            "when": _and(_leaf({"type": "command", "command": "!hello"})),
            "reactions": _seq(_reaction("chat_reply", message="hi there")),
        }
    ]
    bot.trigger_resolver.triggers = bot.settings["triggers"]

    actions = bot.handle_event("chat.message", {"message": "!hello"})

    assert actions == [{"type": "chat_reply", "channel": "#channel", "message": "hi there"}]


def test_twitchbot_resolves_channel_point_reward_trigger():
    bot = TwitchBot(settings_path=None, handlers={"send_chat": lambda channel, message: None})
    bot.settings["triggers"] = [
        {
            "name": "reward_r1",
            "when": _and(_leaf({"type": "channel_point_reward", "reward_id": "r1"})),
            "reactions": _seq(_reaction("chat_reply", message="rewarded")),
        }
    ]
    bot.trigger_resolver.triggers = bot.settings["triggers"]

    actions = bot.handle_event("channel_points.redemption", {"reward_id": "r1"})

    assert actions == [{"type": "chat_reply", "channel": "#channel", "message": "rewarded"}]
