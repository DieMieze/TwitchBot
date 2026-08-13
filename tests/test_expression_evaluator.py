import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.expression import C, evaluate_when, walk_reaction_leaves, walk_trigger_leaves
from twitchbot_runtime.expression.compare import evaluate_compare


def _matcher(condition, event_name, payload, trigger_name):
    return condition.get("type") == event_name


def test_evaluate_and_requires_all_children():
    when = C.and_(C.leaf("event.a"), C.leaf("event.b"))
    assert evaluate_when(when.to_dict(), "event.a", {}, match_condition=_matcher) is False
    # both match only if both children match; here matcher matches single type == event_name
    when2 = C.and_(C.leaf("event.a"), C.leaf("event.a"))
    assert evaluate_when(when2.to_dict(), "event.a", {}, match_condition=_matcher) is True


def test_evaluate_or_matches_any_child():
    when = C.or_(C.leaf("event.a"), C.leaf("event.b"))
    assert evaluate_when(when.to_dict(), "event.b", {}, match_condition=_matcher) is True
    assert evaluate_when(when.to_dict(), "event.c", {}, match_condition=_matcher) is False


def test_evaluate_not_inverts_child():
    when = C.not_(C.leaf("event.a"))
    assert evaluate_when(when.to_dict(), "event.a", {}, match_condition=_matcher) is False
    assert evaluate_when(when.to_dict(), "event.b", {}, match_condition=_matcher) is True


def test_evaluate_nested_and_or_not():
    when = C.or_(
        C.and_(C.leaf("event.a"), C.leaf("event.a")),
        C.not_(C.leaf("event.b")),
    )
    assert evaluate_when(when.to_dict(), "event.a", {}, match_condition=_matcher) is True
    assert evaluate_when(when.to_dict(), "event.b", {}, match_condition=_matcher) is False
    assert evaluate_when(when.to_dict(), "event.c", {}, match_condition=_matcher) is True


def test_evaluate_compare_geq_int():
    when = C.compare("5", ">=", 5)
    assert evaluate_when(when.to_dict(), "e", {}, match_condition=_matcher) is True
    when2 = C.compare("4", ">=", 5)
    assert evaluate_when(when2.to_dict(), "e", {}, match_condition=_matcher) is False


def test_evaluate_compare_with_placeholder_resolution():
    def resolve(text):
        return text.replace("{counter:deaths:value}", "7")

    when = C.compare("{counter:deaths:value}", ">=", 5)
    assert (
        evaluate_when(
            when.to_dict(),
            "e",
            {},
            match_condition=_matcher,
            resolve_placeholder=resolve,
        )
        is True
    )


def test_evaluate_compare_without_resolver_compares_raw():
    when = C.compare("{counter:deaths:value}", ">=", 5)
    assert evaluate_when(when.to_dict(), "e", {}, match_condition=_matcher) is False


def test_evaluate_time_leaf_calls_on_time_match():
    seen = []

    def matcher(condition, event_name, payload, trigger_name):
        return condition.get("type") == "time"

    when = C.and_(C.leaf("time", interval_minutes=5))
    result = evaluate_when(
        when.to_dict(),
        "timer.tick",
        {},
        match_condition=matcher,
        on_time_match=lambda name: seen.append(name),
        trigger_name="t",
    )
    assert result is True
    assert seen == ["t"]


def test_walk_trigger_leaves_collects_conditions():
    when = C.or_(
        C.and_(C.leaf("command", command="!a"), C.leaf("follow")),
        C.not_(C.leaf("time", interval_minutes=5)),
        C.compare("{counter:x:value}", "==", 1),
    )
    leaves = walk_trigger_leaves(when.to_dict())
    types = [leaf.get("type") for leaf in leaves]
    assert types == ["command", "follow", "time", "compare"]


def test_walk_reaction_leaves_collects_reactions():
    from twitchbot_runtime.expression import R

    reactions = R.seq(
        R.reaction("chat_reply", message="hi"),
        R.if_(
            C.leaf("follow"),
            then=R.reaction("overlay_text", text="yes"),
            else_=R.reaction("overlay_gif", gif_id="no"),
        ),
        R.switch(
            "{args[0]}",
            {"red": R.reaction("overlay_gif", gif_id="red")},
            default=R.reaction("chat_reply", message="other"),
        ),
    )
    leaves = walk_reaction_leaves(reactions.to_dict())
    assert [leaf.get("type") for leaf in leaves] == [
        "chat_reply",
        "overlay_text",
        "overlay_gif",
        "overlay_gif",
        "chat_reply",
    ]


def test_compare_eq_neq():
    assert evaluate_compare("red", "==", "red", None) is True
    assert evaluate_compare("red", "!=", "blue", None) is True
    assert evaluate_compare("5", "==", 5, None) is True


def test_compare_in_and_contains():
    assert evaluate_compare("a", "in", ["a", "b"], None) is True
    assert evaluate_compare("a", "in", ["b"], None) is False
    assert evaluate_compare("foobar", "contains", "bar", None) is True
    assert evaluate_compare("foo", "contains", "z", None) is False


def test_compare_regex():
    assert evaluate_compare("hello world", "regex", "wor.d", None) is True
    assert evaluate_compare("hello", "regex", "^wor", None) is False


def test_compare_unknown_op_returns_false():
    assert evaluate_compare("a", "bogus", "a", None) is False
