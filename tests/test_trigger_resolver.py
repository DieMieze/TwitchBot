import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.trigger_resolver import TriggerResolver


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _leaf(condition):
    return {"kind": "leaf", "condition": condition}


def _and(*leaves):
    return {"kind": "and", "children": list(leaves)}


def _or(*leaves):
    return {"kind": "or", "children": list(leaves)}


def _reaction(message="hi", **fields):
    base = {"type": "chat_reply", "message": message}
    base.update(fields)
    return {"kind": "reaction", "reaction": base}


def _seq(*reactions):
    return {"kind": "seq", "children": list(reactions)}


def _command_trigger(name="hello", command="!hello", reactions=None):
    return {
        "name": name,
        "when": _and(_leaf({"type": "command", "command": command})),
        "reactions": reactions or _seq(_reaction("hi")),
    }


def test_command_condition_matches_case_insensitive_prefix():
    trigger = _command_trigger(command="!hello", reactions=_seq(_reaction("hi")))
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!Hello there"})

    assert reactions == [_seq(_reaction("hi"))]


def test_command_condition_no_match_for_different_command():
    trigger = _command_trigger(command="!hello")
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!bye"})

    assert reactions == []


def test_time_condition_fires_on_first_call():
    trigger = {
        "name": "timed",
        "when": _and(_leaf({"type": "time", "interval_minutes": 5})),
        "reactions": _seq(_reaction("tick")),
    }
    clock = FakeClock()
    resolver = TriggerResolver([trigger], time_provider=clock)

    reactions = resolver.resolve("timer.tick", {})

    assert reactions == [_seq(_reaction("tick"))]


def test_time_condition_respects_interval():
    trigger = {
        "name": "timed",
        "when": _and(_leaf({"type": "time", "interval_minutes": 5})),
        "reactions": _seq(_reaction("tick")),
    }
    clock = FakeClock()
    resolver = TriggerResolver([trigger], time_provider=clock)

    first = resolver.resolve("timer.tick", {})
    assert first == [_seq(_reaction("tick"))]

    clock.advance(60)
    second = resolver.resolve("timer.tick", {})
    assert second == []

    clock.advance(5 * 60 - 60)
    third = resolver.resolve("timer.tick", {})
    assert third == [_seq(_reaction("tick"))]


def test_channel_point_reward_condition_matches():
    trigger = {
        "name": "reward",
        "when": _and(_leaf({"type": "channel_point_reward", "reward_id": "abc123"})),
        "reactions": _seq(_reaction("rewarded")),
    }
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("channel_points.redemption", {"reward_id": "abc123"}) == [_seq(_reaction("rewarded"))]
    assert resolver.resolve("channel_points.redemption", {"reward_id": "wrong"}) == []


def test_new_chatter_condition_matches_inactivity_window():
    from twitchbot_runtime.chatter_tracker import ChatterTracker

    trigger = {
        "name": "greet",
        "when": _and(_leaf({"type": "new_chatter", "time": 60})),
        "reactions": _seq(_reaction("Welcome")),
    }
    tracker = ChatterTracker()
    clock = FakeClock()
    resolver = TriggerResolver([trigger], time_provider=clock, chatter_tracker=tracker)

    assert resolver.resolve("chat.message", {"channel": "#c", "username": "Bob"}) == [_seq(_reaction("Welcome"))]

    tracker.record("#c", "Bob", clock())
    clock.advance(10)
    assert resolver.resolve("chat.message", {"channel": "#c", "username": "Bob"}) == []

    clock.advance(60)
    assert resolver.resolve("chat.message", {"channel": "#c", "username": "Bob"}) == [_seq(_reaction("Welcome"))]


def test_new_chatter_without_tracker_returns_false():
    trigger = {
        "name": "greet",
        "when": _and(_leaf({"type": "new_chatter", "time": 60})),
        "reactions": _seq(_reaction("Welcome")),
    }
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("chat.message", {"channel": "#c", "username": "Bob"}) == []


def test_first_time_chatter_condition_matches():
    trigger = {
        "name": "greet",
        "when": _and(_leaf({"type": "first_time_chatter"})),
        "reactions": _seq(_reaction("Welcome")),
    }
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("chat.message", {"is_new_chatter": True}) == [_seq(_reaction("Welcome"))]
    assert resolver.resolve("chat.message", {"is_new_chatter": False}) == []


def test_all_logic_requires_all_conditions():
    trigger = {
        "name": "dc",
        "when": _and(
            _leaf({"type": "command", "command": "!dc"}),
            _leaf({"type": "time", "interval_minutes": 1}),
        ),
        "reactions": _seq(_reaction("dc")),
    }
    clock = FakeClock()
    resolver = TriggerResolver([trigger], time_provider=clock)

    first = resolver.resolve("chat.message", {"message": "!dc"})
    assert first == [_seq(_reaction("dc"))]

    clock.advance(10)
    second = resolver.resolve("chat.message", {"message": "!dc"})
    assert second == []


def test_any_logic_matches_at_least_one():
    trigger = {
        "name": "color",
        "when": _or(
            _leaf({"type": "command", "command": "!green"}),
            _leaf({"type": "command", "command": "!red"}),
        ),
        "reactions": _seq(_reaction("color")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!red"})

    assert reactions == [_seq(_reaction("color"))]


def test_event_filter_skips_non_matching_events():
    trigger = {
        "name": "follows",
        "event": "event.follow",
        "when": _and(),
        "reactions": _seq(_reaction("thanks")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("event.sub", {})

    assert reactions == []


def test_trigger_name_filter():
    specific = {
        "name": "specific",
        "when": _and(),
        "reactions": _seq(_reaction("specific")),
    }
    other = {
        "name": "other",
        "when": _and(),
        "reactions": _seq(_reaction("other")),
    }
    resolver = TriggerResolver([specific, other])

    reactions = resolver.resolve("event.test", {"trigger_name": "specific"})

    assert reactions == [_seq(_reaction("specific"))]


def test_list_triggers_returns_summaries():
    triggers = [
        {
            "name": "alpha",
            "event": "chat.message",
            "when": _and(
                _leaf({"type": "command", "command": "!a"}),
                _leaf({"type": "time", "interval_minutes": 5}),
            ),
            "reactions": _seq(),
        },
        {
            "name": "beta",
            "when": _and(_leaf({"type": "channel_point_reward", "reward_id": "x"})),
            "reactions": _seq(),
        },
    ]
    resolver = TriggerResolver(triggers)

    summaries = resolver.list_triggers()

    assert summaries == [
        {"name": "alpha", "event": "chat.message", "conditions_count": 2},
        {"name": "beta", "event": None, "conditions_count": 1},
    ]


def test_roles_vip_matches_when_payload_has_vip():
    trigger = {
        "name": "vip_only",
        "when": _and(_leaf({"type": "command", "command": "!vip"})),
        "roles": ["vip"],
        "reactions": _seq(_reaction("vip")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!vip", "roles": ["vip"]})

    assert reactions == [_seq(_reaction("vip"))]


def test_roles_vip_blocks_when_payload_lacks_vip():
    trigger = {
        "name": "vip_only",
        "when": _and(_leaf({"type": "command", "command": "!vip"})),
        "roles": ["vip"],
        "reactions": _seq(_reaction("vip")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!vip", "roles": ["subscriber"]})

    assert reactions == []


def test_roles_subscriber_matches_when_payload_has_subscriber():
    trigger = {
        "name": "sub_only",
        "when": _and(_leaf({"type": "command", "command": "!sub"})),
        "roles": ["subscriber"],
        "reactions": _seq(_reaction("sub")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!sub", "roles": ["subscriber"]})

    assert reactions == [_seq(_reaction("sub"))]


def test_roles_everyone_list_always_allowed_without_payload_roles():
    trigger = {
        "name": "everyone_list",
        "when": _and(_leaf({"type": "command", "command": "!hi"})),
        "roles": ["everyone"],
        "reactions": _seq(_reaction("hi")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!hi"})

    assert reactions == [_seq(_reaction("hi"))]


def test_roles_everyone_bare_string_always_allowed():
    trigger = {
        "name": "everyone_string",
        "when": _and(_leaf({"type": "command", "command": "!hi"})),
        "roles": "everyone",
        "reactions": _seq(_reaction("hi")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!hi"})

    assert reactions == [_seq(_reaction("hi"))]


def test_roles_everyone_list_allowed_even_with_payload_roles():
    trigger = {
        "name": "everyone_with_roles",
        "when": _and(_leaf({"type": "command", "command": "!hi"})),
        "roles": ["everyone"],
        "reactions": _seq(_reaction("hi")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!hi", "roles": ["subscriber"]})

    assert reactions == [_seq(_reaction("hi"))]


def test_roles_broadcaster_override_with_vip_requirement():
    trigger = {
        "name": "vip_or_bc",
        "when": _and(_leaf({"type": "command", "command": "!x"})),
        "roles": ["vip"],
        "reactions": _seq(_reaction("x")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!x", "roles": ["broadcaster"]})

    assert reactions == [_seq(_reaction("x"))]


def test_roles_vip_via_badge_mapping():
    trigger = {
        "name": "vip_via_badge",
        "when": _and(_leaf({"type": "command", "command": "!v"})),
        "roles": ["vip"],
        "reactions": _seq(_reaction("v")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!v", "badges": [{"id": "vip"}]})

    assert reactions == [_seq(_reaction("v"))]


def test_roles_subscriber_via_badge_mapping():
    trigger = {
        "name": "sub_via_badge",
        "when": _and(_leaf({"type": "command", "command": "!s"})),
        "roles": ["subscriber"],
        "reactions": _seq(_reaction("s")),
    }
    resolver = TriggerResolver([trigger])

    reactions = resolver.resolve("chat.message", {"message": "!s", "badges": [{"id": "subscriber"}]})

    assert reactions == [_seq(_reaction("s"))]


def test_not_node_inverts_leaf():
    trigger = {
        "name": "not_follow",
        "when": _and(
            _leaf({"type": "command", "command": "!nf"}),
            {"kind": "not", "child": _leaf({"type": "follow"})},
        ),
        "reactions": _seq(_reaction("nf")),
    }
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("chat.message", {"message": "!nf"}) == [_seq(_reaction("nf"))]
    assert resolver.resolve("event.follow", {"message": "!nf"}) == []


def test_nested_and_or_not_tree():
    trigger = {
        "name": "nested",
        "when": _or(
            _and(_leaf({"type": "command", "command": "!a"}), _leaf({"type": "command", "command": "!a"})),
            {"kind": "not", "child": _leaf({"type": "follow"})},
        ),
        "reactions": _seq(_reaction("nested")),
    }
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("chat.message", {"message": "!a"}) == [_seq(_reaction("nested"))]
    assert resolver.resolve("event.follow", {}) == []
    assert resolver.resolve("event.sub", {}) == [_seq(_reaction("nested"))]


def test_empty_and_matches_empty_or_does_not():
    and_trigger = {
        "name": "a",
        "when": _and(),
        "reactions": _seq(_reaction("a")),
    }
    or_trigger = {
        "name": "o",
        "when": _or(),
        "reactions": _seq(_reaction("o")),
    }
    resolver = TriggerResolver([and_trigger, or_trigger])

    assert resolver.resolve("e", {}) == [_seq(_reaction("a"))]


def test_compare_leaf_geq_int():
    trigger = {
        "name": "cmp",
        "when": _and(
            _leaf({"type": "command", "command": "!c"}),
            _leaf({"type": "compare", "field": "5", "op": ">=", "value": 5}),
        ),
        "reactions": _seq(_reaction("c")),
    }
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("chat.message", {"message": "!c"}) == [_seq(_reaction("c"))]


def test_compare_leaf_with_counter_handler():
    class CounterStub:
        def resolve_placeholders(self, message):
            return message.replace("{counter:deaths:value}", "7")

    trigger = {
        "name": "cmpc",
        "when": _and(
            _leaf({"type": "command", "command": "!c"}),
            _leaf({"type": "compare", "field": "{counter:deaths:value}", "op": ">=", "value": 5}),
        ),
        "reactions": _seq(_reaction("c")),
    }
    resolver = TriggerResolver([trigger], counter_handler=CounterStub())

    assert resolver.resolve("chat.message", {"message": "!c"}) == [_seq(_reaction("c"))]


def test_compare_leaf_without_counter_handler_compares_raw():
    trigger = {
        "name": "cmpn",
        "when": _and(
            _leaf({"type": "command", "command": "!c"}),
            _leaf({"type": "compare", "field": "{counter:deaths:value}", "op": ">=", "value": 5}),
        ),
        "reactions": _seq(_reaction("c")),
    }
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("chat.message", {"message": "!c"}) == []


def test_time_leaf_nested_in_and_triggers_cooldown():
    trigger = {
        "name": "ct",
        "when": _and(
            _leaf({"type": "command", "command": "!t"}),
            _leaf({"type": "time", "interval_minutes": 1}),
        ),
        "reactions": _seq(_reaction("t")),
    }
    clock = FakeClock()
    resolver = TriggerResolver([trigger], time_provider=clock)

    first = resolver.resolve("chat.message", {"message": "!t"})
    assert first == [_seq(_reaction("t"))]

    clock.advance(10)
    second = resolver.resolve("chat.message", {"message": "!t"})
    assert second == []
