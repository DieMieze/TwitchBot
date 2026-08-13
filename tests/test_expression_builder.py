import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.expression import And, C, Not, Or, R


def test_builder_trigger_roundtrip_to_dict():
    when = C.and_(
        C.leaf("command", command="!so"),
        C.not_(C.leaf("cheer", min_bits=100)),
        C.compare("{counter:deaths:value}", ">=", 5),
    )
    expected = {
        "kind": "and",
        "children": [
            {"kind": "leaf", "condition": {"type": "command", "command": "!so"}},
            {
                "kind": "not",
                "child": {
                    "kind": "leaf",
                    "condition": {"type": "cheer", "min_bits": 100},
                },
            },
            {
                "kind": "leaf",
                "condition": {
                    "type": "compare",
                    "field": "{counter:deaths:value}",
                    "op": ">=",
                    "value": 5,
                },
            },
        ],
    }
    assert when.to_dict() == expected


def test_builder_reaction_roundtrip_to_dict():
    reactions = R.seq(
        R.if_(
            C.leaf("follow"),
            then=R.reaction("chat_reply", message="Welcome!"),
            else_=R.reaction("overlay_text", text="no follow"),
        ),
        R.switch(
            "{args[0]}",
            {"red": R.reaction("overlay_gif", gif_id="red")},
            default=R.reaction("chat_reply", message="unknown color"),
        ),
    )
    expected = {
        "kind": "seq",
        "children": [
            {
                "kind": "if",
                "when": {"kind": "leaf", "condition": {"type": "follow"}},
                "then": {
                    "kind": "reaction",
                    "reaction": {"type": "chat_reply", "message": "Welcome!"},
                },
                "else": {
                    "kind": "reaction",
                    "reaction": {"type": "overlay_text", "text": "no follow"},
                },
            },
            {
                "kind": "switch",
                "on": "{args[0]}",
                "cases": [
                    {
                        "equals": "red",
                        "then": {
                            "kind": "reaction",
                            "reaction": {"type": "overlay_gif", "gif_id": "red"},
                        },
                    }
                ],
                "default": {
                    "kind": "reaction",
                    "reaction": {"type": "chat_reply", "message": "unknown color"},
                },
            },
        ],
    }
    assert reactions.to_dict() == expected


def test_trigger_node_from_dict_roundtrip():
    when = C.or_(
        C.leaf("command", command="!hi"),
        C.and_(C.leaf("follow"), C.not_(C.leaf("sub"))),
    )
    serialized = when.to_dict()
    from twitchbot_runtime.expression.nodes import TriggerNode

    restored = TriggerNode.from_dict(serialized)
    assert restored.to_dict() == serialized


def test_reaction_node_from_dict_roundtrip():
    reactions = R.seq(
        R.reaction("chat_reply", message="hi"),
        R.switch(
            "{args[0]}",
            {"a": R.reaction("overlay_text", text="A")},
            default=R.reaction("overlay_text", text="other"),
        ),
    )
    serialized = reactions.to_dict()
    from twitchbot_runtime.expression.nodes import ReactionAstNode

    restored = ReactionAstNode.from_dict(serialized)
    assert restored.to_dict() == serialized


def test_all_any_aliases_normalize_to_and_or():
    from twitchbot_runtime.expression.nodes import TriggerNode

    node = TriggerNode.from_dict({"kind": "all", "children": []})
    assert isinstance(node, And)
    node = TriggerNode.from_dict({"kind": "any", "children": []})
    assert isinstance(node, Or)


def test_empty_and_true_empty_or_false():
    from twitchbot_runtime.expression.evaluator import evaluate_when

    matcher = lambda condition, event_name, payload, trigger_name: False  # noqa: E731
    assert evaluate_when(C.and_().to_dict(), "e", {}, match_condition=matcher) is True
    assert evaluate_when(C.or_().to_dict(), "e", {}, match_condition=matcher) is False


def test_not_requires_child():
    from twitchbot_runtime.expression.nodes import TriggerNode

    not_node = Not(child=None)
    serialized = not_node.to_dict()
    assert serialized["child"] is None
    restored = TriggerNode.from_dict(serialized)
    assert restored.child is None
