import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.expression.condition_match import (
    match_event_condition,
    matches_roles,
    payload_roles,
)
from twitchbot_runtime.expression.evaluator import evaluate_reaction_ast, walk_trigger_leaves


def _ctx_match(condition, event_name="chat.message", payload=None):
    return match_event_condition(
        condition,
        event_name,
        payload or {},
        "t",
        time_provider=lambda: 0.0,
        last_trigger_times={},
        chatter_tracker=None,
    )


def test_role_leaf_mod_matches():
    assert _ctx_match({"type": "role", "roles": ["mod"]}, payload={"roles": ["mod"]}) is True


def test_role_leaf_mod_does_not_match_vip():
    assert _ctx_match({"type": "role", "roles": ["mod"]}, payload={"roles": ["vip"]}) is False


def test_role_leaf_broadcaster_matches_self():
    assert _ctx_match({"type": "role", "roles": ["broadcaster"]}, payload={"roles": ["broadcaster"]}) is True


def test_role_leaf_broadcaster_does_not_match_mod():
    assert _ctx_match({"type": "role", "roles": ["broadcaster"]}, payload={"roles": ["mod"]}) is False


def test_role_leaf_broadcaster_override_passes_mod_required():
    assert _ctx_match({"type": "role", "roles": ["mod"]}, payload={"roles": ["broadcaster"]}) is True


def test_role_leaf_empty_roles_is_no_restriction():
    assert _ctx_match({"type": "role", "roles": []}, payload={"roles": ["vip"]}) is True
    assert _ctx_match({"type": "role", "roles": []}, payload={}) is True


def test_role_leaf_string_roles_normalizes():
    assert _ctx_match({"type": "role", "roles": "mod"}, payload={"roles": ["mod"]}) is True


def test_role_leaf_derives_roles_from_badges():
    assert _ctx_match(
        {"type": "role", "roles": ["mod"]},
        payload={"badges": [{"id": "moderator"}]},
    ) is True


def test_matches_roles_broadcaster_override():
    assert matches_roles({"roles": ["mod"]}, ["broadcaster"]) is True
    assert matches_roles({"roles": ["mod"]}, ["vip"]) is False
    assert matches_roles({"roles": []}, []) is True
    assert matches_roles({"roles": ["everyone"]}, []) is True


def test_payload_roles_from_badges():
    assert payload_roles({"badges": [{"id": "moderator"}, {"id": "vip"}]}) == ["mod", "vip"]


def test_if_when_role_leaf_then_branch_taken():
    class FakeEngine:
        def _match_condition(self, condition, event_name, payload, trigger_name):
            return match_event_condition(
                condition, event_name, payload, trigger_name,
                time_provider=lambda: 0.0,
                last_trigger_times={},
                chatter_tracker=None,
            )

        def execute(self, reactions, context=None):
            return [{"executed": reactions, "context": context}]

    engine = FakeEngine()
    ast = {
        "kind": "if",
        "when": {"kind": "leaf", "condition": {"type": "role", "roles": ["mod"]}},
        "then": {"kind": "reaction", "reaction": {"type": "chat_reply", "message": "ok"}},
        "else": {"kind": "reaction", "reaction": {"type": "chat_reply", "message": "no"}},
    }

    results = evaluate_reaction_ast(
        ast, {"roles": ["mod"]}, engine, lambda s: s
    )
    assert results[0]["executed"][0]["message"] == "ok"

    results = evaluate_reaction_ast(
        ast, {"roles": ["vip"]}, engine, lambda s: s
    )
    assert results[0]["executed"][0]["message"] == "no"


def test_walk_trigger_leaves_includes_role_leaf():
    when = {
        "kind": "and",
        "children": [
            {"kind": "leaf", "condition": {"type": "command", "command": "!x"}},
            {"kind": "leaf", "condition": {"type": "role", "roles": ["broadcaster"]}},
        ],
    }
    leaves = walk_trigger_leaves(when)
    types = [leaf.get("type") for leaf in leaves]
    assert "role" in types
    assert "command" in types
