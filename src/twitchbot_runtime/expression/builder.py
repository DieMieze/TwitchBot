"""Code-DSL builders for the nested trigger/reaction trees.

``C`` builds trigger nodes (AND/OR/NOT/leaf/compare); ``R`` builds reaction
AST nodes (seq/if/switch/reaction). Every builder returns a dataclass from
:mod:`expression.nodes`; call ``.to_dict()`` to get the serializable
``{"kind": ...}`` form written into ``settings.json``.

Full example::

    from twitchbot_runtime.expression import C, R

    when = C.and_(
        C.leaf("command", command="!so"),
        C.not_(C.leaf("cheer", min_bits=100)),
        C.compare("{counter:deaths:value}", ">=", 5),
    )
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
    trigger = {
        "name": "so",
        "when": when.to_dict(),
        "roles": [],
        "reactions": reactions.to_dict(),
    }
"""

from __future__ import annotations

from typing import Any

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


class C:
    """Condition (trigger-tree) builder."""

    @staticmethod
    def and_(*children: TriggerNode) -> And:
        return And(children=list(children))

    @staticmethod
    def or_(*children: TriggerNode) -> Or:
        return Or(children=list(children))

    @staticmethod
    def not_(child: TriggerNode) -> Not:
        return Not(child=child)

    @staticmethod
    def leaf(type_: str, **fields: Any) -> Leaf:
        condition = {"type": type_, **fields}
        return Leaf(condition=condition)

    @staticmethod
    def compare(field: str, op: str, value: Any) -> Leaf:
        return Leaf(condition={"type": "compare", "field": field, "op": op, "value": value})


class R:
    """Reaction AST builder."""

    @staticmethod
    def seq(*children: ReactionAstNode) -> Seq:
        return Seq(children=list(children))

    @staticmethod
    def if_(
        when: TriggerNode,
        *,
        then: ReactionAstNode | None = None,
        else_: ReactionAstNode | None = None,
    ) -> If:
        return If(when=when, then=then, else_=else_)

    @staticmethod
    def switch(
        on: str,
        cases: dict[Any, ReactionAstNode],
        *,
        default: ReactionAstNode | None = None,
    ) -> Switch:
        case_list = [SwitchCase(equals=key, then=value) for key, value in cases.items()]
        return Switch(on=on, cases=case_list, default=default)

    @staticmethod
    def reaction(type_: str, **fields: Any) -> ReactionNode:
        return ReactionNode(reaction={"type": type_, **fields})
