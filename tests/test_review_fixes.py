import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.counter_handler import CounterHandler
from twitchbot_runtime.eventsub.events import normalize_event
from twitchbot_runtime.reaction_engine import ReactionEngine
from twitchbot_runtime.trigger_resolver import TriggerResolver


def _engine(counter_handler, send_chat):
    return ReactionEngine(
        send_chat=send_chat,
        overlay_dispatch=lambda action: None,
        create_clip=lambda: "",
        counter_handler=counter_handler,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: None,
    )


def test_chat_reply_resolves_username_placeholder():
    sent = []
    engine = _engine(CounterHandler(store_path=Path("counters.json")), lambda c, m: sent.append((c, m)))

    engine.execute(
        [{"type": "chat_reply", "message": "Hallo {username}!"}],
        context={"username": "Mayle"},
    )

    assert sent == [("#channel", "Hallo Mayle!")]


def test_chat_reply_resolves_counter_placeholder(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})
    handler.handle("increment", {"name": "deaths", "amount": 5})
    sent = []
    engine = _engine(handler, lambda c, m: sent.append((c, m)))

    engine.execute(
        [{"type": "chat_reply", "message": "Tode: {counter:deaths:value}"}],
        context={"username": "Mayle"},
    )

    assert sent == [("#channel", "Tode: 5")]


def test_chat_reply_leaves_unknown_counter_placeholder_intact(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    sent = []
    engine = _engine(handler, lambda c, m: sent.append((c, m)))

    engine.execute(
        [{"type": "chat_reply", "message": "{counter:ghost:value}"}],
        context={},
    )

    assert sent == [("#channel", "{counter:ghost:value}")]


def test_chat_reply_resolves_username_and_counter_together(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})
    handler.handle("increment", {"name": "deaths", "amount": 3})
    sent = []
    engine = _engine(handler, lambda c, m: sent.append((c, m)))

    engine.execute(
        [{"type": "chat_reply", "message": "{username} deaths: {counter:deaths:value}"}],
        context={"username": "Alice"},
    )

    assert sent == [("#channel", "Alice deaths: 3")]


def test_chat_reply_resolves_subcounter_placeholder(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "bosses"})
    handler.handle("add_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    handler.handle("select_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    sent = []
    engine = _engine(handler, lambda c, m: sent.append((c, m)))

    engine.execute(
        [{"type": "chat_reply", "message": "boss1: {counter:bosses:subcounter_value}"}],
        context={},
    )

    assert sent == [("#channel", "boss1: 0")]


def test_roles_blocks_trigger_when_payload_missing_roles():
    trigger = {
        "name": "purge",
        "when": {
            "kind": "and",
            "children": [{"kind": "leaf", "condition": {"type": "command", "command": "!purge"}}],
        },
        "roles": ["mod", "broadcaster"],
        "reactions": {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "moderation", "action": "purge"}}],
        },
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!purge"})

    assert reactions == []


def test_roles_allows_trigger_when_payload_has_required_role():
    trigger = {
        "name": "purge",
        "when": {
            "kind": "and",
            "children": [{"kind": "leaf", "condition": {"type": "command", "command": "!purge"}}],
        },
        "roles": ["mod", "broadcaster"],
        "reactions": {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "moderation", "action": "purge"}}],
        },
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!purge", "roles": ["mod"]})

    assert reactions == [
        {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "moderation", "action": "purge"}}],
        }
    ]


def test_roles_allows_trigger_for_broadcaster_even_if_not_listed():
    trigger = {
        "name": "purge",
        "when": {
            "kind": "and",
            "children": [{"kind": "leaf", "condition": {"type": "command", "command": "!purge"}}],
        },
        "roles": ["mod"],
        "reactions": {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "moderation", "action": "purge"}}],
        },
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!purge", "roles": ["broadcaster"]})

    assert reactions == [
        {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "moderation", "action": "purge"}}],
        }
    ]


def test_roles_allows_trigger_via_badges_mapping():
    trigger = {
        "name": "purge",
        "when": {
            "kind": "and",
            "children": [{"kind": "leaf", "condition": {"type": "command", "command": "!purge"}}],
        },
        "roles": ["mod", "broadcaster"],
        "reactions": {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "moderation", "action": "purge"}}],
        },
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve(
        "chat.message",
        {"message": "!purge", "badges": [{"id": "moderator"}]},
    )

    assert reactions == [
        {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "moderation", "action": "purge"}}],
        }
    ]


def test_roles_no_restrictions_allows_everyone():
    trigger = {
        "name": "hello",
        "when": {
            "kind": "and",
            "children": [{"kind": "leaf", "condition": {"type": "command", "command": "!hello"}}],
        },
        "roles": [],
        "reactions": {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "chat_reply", "message": "hi"}}],
        },
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!hello"})

    assert reactions == [
        {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "chat_reply", "message": "hi"}}],
        }
    ]


def test_first_time_chatter_trigger_fires_when_payload_is_new_chatter():
    trigger = {
        "name": "greet",
        "when": {
            "kind": "and",
            "children": [{"kind": "leaf", "condition": {"type": "first_time_chatter"}}],
        },
        "reactions": {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "chat_reply", "message": "Welcome {username}!"}}],
        },
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"is_new_chatter": True, "username": "Bob"})

    assert reactions == [
        {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "chat_reply", "message": "Welcome {username}!"}}],
        }
    ]


def test_first_time_chatter_trigger_does_not_fire_for_regular_chatter():
    trigger = {
        "name": "greet",
        "when": {
            "kind": "and",
            "children": [{"kind": "leaf", "condition": {"type": "first_time_chatter"}}],
        },
        "reactions": {
            "kind": "seq",
            "children": [{"kind": "reaction", "reaction": {"type": "chat_reply", "message": "Welcome"}}],
        },
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"is_new_chatter": False})

    assert reactions == []


def test_normalize_chat_message_extracts_chatter_is_new():
    event = {
        "broadcaster_user_login": "streamer",
        "chatter_user_name": "viewer",
        "chatter_is_new": True,
        "message": {"text": "!hello"},
    }

    name, payload = normalize_event("channel.chat.message", event)

    assert name == "chat.message"
    assert payload["is_new_chatter"] is True


def test_normalize_chat_message_defaults_is_new_chatter_false():
    event = {
        "broadcaster_user_login": "streamer",
        "chatter_user_name": "viewer",
        "message": {"text": "!hello"},
    }

    name, payload = normalize_event("channel.chat.message", event)

    assert payload["is_new_chatter"] is False


def test_normalize_chat_message_maps_badges_to_roles():
    event = {
        "broadcaster_user_login": "streamer",
        "chatter_user_name": "mod_user",
        "message": {"text": "!purge"},
        "badges": [{"id": "moderator"}, {"id": "vip"}],
    }

    name, payload = normalize_event("channel.chat.message", event)

    assert payload["roles"] == ["mod", "vip"]
    assert payload["badges"] == ["moderator", "vip"]


def test_normalize_chat_message_maps_broadcaster_badge_to_role():
    event = {
        "broadcaster_user_login": "streamer",
        "chatter_user_name": "streamer",
        "message": {"text": "!hello"},
        "badges": [{"id": "broadcaster"}],
    }

    name, payload = normalize_event("channel.chat.message", event)

    assert payload["roles"] == ["broadcaster"]


def test_normalize_chat_message_maps_subscriber_badge_to_role():
    event = {
        "broadcaster_user_login": "streamer",
        "chatter_user_name": "sub_user",
        "message": {"text": "!hello"},
        "badges": [{"id": "subscriber"}],
    }

    name, payload = normalize_event("channel.chat.message", event)

    assert payload["roles"] == ["subscriber"]
    assert payload["badges"] == ["subscriber"]


def test_webui_reaction_handled_and_not_unknown():
    engine = _engine(CounterHandler(store_path=Path("counters.json")), lambda c, m: None)

    actions = engine.execute([{"type": "webui", "status": "online"}])

    assert len(actions) == 1
    assert actions[0]["type"] == "webui"
    assert actions[0]["payload"] == {"status": "online"}
