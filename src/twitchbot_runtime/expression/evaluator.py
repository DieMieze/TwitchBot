from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .compare import evaluate_compare
from .nodes import (
    And,
    If,
    Leaf,
    Not,
    Or,
    ReactionAstNode,
    ReactionNode,
    Seq,
    Switch,
    SwitchCase,
    TriggerNode,
)

ResolvePlaceholder = Callable[[str], str]


def evaluate_when(
    node: Any,
    event_name: str,
    payload: dict[str, Any],
    *,
    match_condition: Callable[..., bool],
    resolve_placeholder: ResolvePlaceholder | None = None,
    on_time_match: Callable[[str], None] | None = None,
    trigger_name: str = "",
) -> bool:
    """Recursively evaluate a trigger tree (TriggerNode) against an event.

    ``match_condition`` is a callable
    ``(condition, event_name, payload, trigger_name) -> bool`` used for the 8
    event-type leaves (resolver-side and engine-side callers inject their own
    binding). ``compare`` leaves are handled here via :mod:`compare`.

    ``resolve_placeholder`` resolves placeholders inside a ``compare`` leaf's
    ``field`` (e.g. ``{counter:...}``, ``{args[N]}``). When ``None``, the field
    is compared as-is.

    ``on_time_match`` (optional) is invoked with the trigger name when a
    ``time`` leaf matches, so the caller can record the cooldown timestamp.
    """
    if node is None:
        return True
    if isinstance(node, dict):
        node = TriggerNode.from_dict(node)

    if isinstance(node, And):
        return all(
            evaluate_when(
                child,
                event_name,
                payload,
                match_condition=match_condition,
                resolve_placeholder=resolve_placeholder,
                on_time_match=on_time_match,
                trigger_name=trigger_name,
            )
            for child in node.children
        )

    if isinstance(node, Or):
        return any(
            evaluate_when(
                child,
                event_name,
                payload,
                match_condition=match_condition,
                resolve_placeholder=resolve_placeholder,
                on_time_match=on_time_match,
                trigger_name=trigger_name,
            )
            for child in node.children
        )

    if isinstance(node, Not):
        if node.child is None:
            return False
        return not evaluate_when(
            node.child,
            event_name,
            payload,
            match_condition=match_condition,
            resolve_placeholder=resolve_placeholder,
            on_time_match=on_time_match,
            trigger_name=trigger_name,
        )

    if isinstance(node, Leaf):
        condition = node.condition or {}
        cond_type = condition.get("type")

        if cond_type == "compare":
            field = condition.get("field", "")
            op = condition.get("op", "==")
            value = condition.get("value")
            return evaluate_compare(str(field), str(op), value, resolve_placeholder)

        result = match_condition(condition, event_name, payload, trigger_name)
        if cond_type == "time" and result and on_time_match is not None:
            on_time_match(trigger_name)
        return result

    return False


def walk_trigger_leaves(node: Any) -> list[dict[str, Any]]:
    """Yield every leaf ``condition`` dict in a trigger tree (depth-first)."""
    if node is None:
        return []
    if isinstance(node, dict):
        node = TriggerNode.from_dict(node)

    leaves: list[dict[str, Any]] = []
    if isinstance(node, And) or isinstance(node, Or):
        for child in node.children:
            leaves.extend(walk_trigger_leaves(child))
    elif isinstance(node, Not):
        if node.child is not None:
            leaves.extend(walk_trigger_leaves(node.child))
    elif isinstance(node, Leaf):
        leaves.append(dict(node.condition))
    return leaves


def walk_reaction_leaves(node: Any) -> list[dict[str, Any]]:
    """Yield every ``reaction`` leaf dict in a reaction AST (depth-first)."""
    if node is None:
        return []
    if isinstance(node, dict):
        node = ReactionAstNode.from_dict(node)

    leaves: list[dict[str, Any]] = []
    if isinstance(node, Seq):
        for child in node.children:
            leaves.extend(walk_reaction_leaves(child))
    elif isinstance(node, If):
        if node.then is not None:
            leaves.extend(walk_reaction_leaves(node.then))
        if node.else_ is not None:
            leaves.extend(walk_reaction_leaves(node.else_))
    elif isinstance(node, Switch):
        for case in node.cases:
            if case.then is not None:
                leaves.extend(walk_reaction_leaves(case.then))
        if node.default is not None:
            leaves.extend(walk_reaction_leaves(node.default))
    elif isinstance(node, ReactionNode):
        leaves.append(dict(node.reaction))
    return leaves


def evaluate_reaction_ast(
    node: Any,
    context: dict[str, Any],
    engine: Any,
    resolve_placeholder: ResolvePlaceholder,
) -> list[dict[str, Any]]:
    """Recursively evaluate a reaction AST against the engine.

    Returns a flat list of reaction-result dicts (same shape as
    ``ReactionEngine.execute``). ``engine`` must expose ``execute(list, context)``
    used to dispatch the leaf ``reaction`` dicts. IF/SWITCH use
    :func:`evaluate_when` with the engine-side ``resolve_placeholder`` (which
    includes counter resolution).
    """
    if node is None:
        return []
    if isinstance(node, dict):
        node = ReactionAstNode.from_dict(node)

    if isinstance(node, Seq):
        results: list[dict[str, Any]] = []
        for child in node.children:
            results.extend(evaluate_reaction_ast(child, context, engine, resolve_placeholder))
        return results

    if isinstance(node, If):
        when_node = node.when
        condition_holds = evaluate_when(
            when_node,
            context.get("event_name", ""),
            context,
            match_condition=engine._match_condition,
            resolve_placeholder=resolve_placeholder,
        )
        branch = node.then if condition_holds else node.else_
        return evaluate_reaction_ast(branch, context, engine, resolve_placeholder) if branch is not None else []

    if isinstance(node, Switch):
        on_value = node.on
        if callable(resolve_placeholder):
            try:
                on_value = resolve_placeholder(on_value)
            except Exception:
                on_value = on_value
        for case in node.cases:
            if _switch_case_matches(on_value, case):
                return evaluate_reaction_ast(case.then, context, engine, resolve_placeholder) if case.then is not None else []
        return (
            evaluate_reaction_ast(node.default, context, engine, resolve_placeholder)
            if node.default is not None
            else []
        )

    if isinstance(node, ReactionNode):
        return engine.execute([dict(node.reaction)], context=context)

    return []


def _switch_case_matches(on_value: Any, case: SwitchCase) -> bool:
    left, right = on_value, case.equals
    try:
        if str(left) == str(right):
            return True
    except Exception:
        pass
    return False
