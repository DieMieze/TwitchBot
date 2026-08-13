import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.trigger_resolver import TriggerResolver


def _leaf(condition):
    return {"kind": "leaf", "condition": condition}


def _and(*leaves):
    return {"kind": "and", "children": list(leaves)}


def _reaction(message, **fields):
    base = {"type": "chat_reply", "message": message}
    base.update(fields)
    return {"kind": "reaction", "reaction": base}


def _seq(*reactions):
    return {"kind": "seq", "children": list(reactions)}


def _trigger(name, condition, reactions):
    return {
        "name": name,
        "when": _and(_leaf(condition)),
        "reactions": reactions,
    }


def test_follow_condition_matches_on_event_follow():
    trigger = _trigger("thanks_follow", {"type": "follow"}, _seq(_reaction("thanks")))
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("event.follow", {"username": "newfollower"}) == [_seq(_reaction("thanks"))]
    assert resolver.resolve("event.sub", {"username": "newfollower"}) == []


def test_sub_condition_matches_on_event_sub():
    trigger = _trigger("thanks_sub", {"type": "sub"}, _seq(_reaction("subbed")))
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("event.sub", {"username": "subber"}) == [_seq(_reaction("subbed"))]
    assert resolver.resolve("event.follow", {"username": "subber"}) == []


def test_cheer_condition_matches_without_min_bits():
    trigger = _trigger("cheer_any", {"type": "cheer"}, _seq(_reaction("cheered")))
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("event.cheer", {"username": "a", "bits": 1}) == [_seq(_reaction("cheered"))]


def test_cheer_condition_filters_by_min_bits():
    trigger = _trigger("big_cheer", {"type": "cheer", "min_bits": 100}, _seq(_reaction("big")))
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("event.cheer", {"username": "a", "bits": 50}) == []
    assert resolver.resolve("event.cheer", {"username": "a", "bits": 100}) == [_seq(_reaction("big"))]
    assert resolver.resolve("event.cheer", {"username": "a", "bits": 500}) == [_seq(_reaction("big"))]


def test_cheer_condition_min_bits_zero_or_negative_means_no_filter():
    trigger = _trigger("cheer_all", {"type": "cheer", "min_bits": 0}, _seq(_reaction("any")))
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("event.cheer", {"bits": 1}) == [_seq(_reaction("any"))]


def test_raid_condition_matches_without_min_viewers():
    trigger = _trigger("raid_any", {"type": "raid"}, _seq(_reaction("raid")))
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("event.raid", {"username": "raider", "viewers": 5}) == [_seq(_reaction("raid"))]


def test_raid_condition_filters_by_min_viewers():
    trigger = _trigger("big_raid", {"type": "raid", "min_viewers": 50}, _seq(_reaction("bigraid")))
    resolver = TriggerResolver([trigger])

    assert resolver.resolve("event.raid", {"viewers": 10}) == []
    assert resolver.resolve("event.raid", {"viewers": 50}) == [_seq(_reaction("bigraid"))]
    assert resolver.resolve("event.raid", {"viewers": 500}) == [_seq(_reaction("bigraid"))]


def test_command_match_extracts_args_into_payload():
    trigger = _trigger(
        "ban_cmd",
        {"type": "command", "command": "!ban"},
        _seq({"kind": "reaction", "reaction": {"type": "moderation", "action": "ban", "target": "{args[0]}"}}),
    )
    resolver = TriggerResolver([trigger])
    payload = {"message": "!ban spammer reason"}

    reactions = resolver.resolve("chat.message", payload)

    assert reactions == [
        _seq({"kind": "reaction", "reaction": {"type": "moderation", "action": "ban", "target": "{args[0]}"}})
    ]
    assert payload["args"] == ["spammer", "reason"]


def test_command_match_no_args_yields_empty_list():
    trigger = _trigger("hello", {"type": "command", "command": "!hello"}, _seq(_reaction("hi")))
    resolver = TriggerResolver([trigger])
    payload = {"message": "!hello"}

    resolver.resolve("chat.message", payload)

    assert payload["args"] == []


def test_non_command_trigger_does_not_inject_args():
    trigger = _trigger("follow_thanks", {"type": "follow"}, _seq(_reaction("thanks")))
    resolver = TriggerResolver([trigger])
    payload = {"username": "follower", "message": "!hello world"}

    resolver.resolve("event.follow", payload)

    assert "args" not in payload


def test_command_match_case_insensitive_but_args_preserve_case():
    trigger = _trigger("ban", {"type": "command", "command": "!BAN"}, _seq(_reaction("banned")))
    resolver = TriggerResolver([trigger])
    payload = {"message": "!ban SpammerUser"}

    resolver.resolve("chat.message", payload)

    assert payload["args"] == ["SpammerUser"]
