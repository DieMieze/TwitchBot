from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_TRIGGER_KIND_ALIASES = {
    "all": "and",
    "any": "or",
}


def _normalize_trigger_kind(kind: str) -> str:
    return _TRIGGER_KIND_ALIASES.get(kind, kind)


@dataclass
class TriggerNode:
    """Base dataclass for trigger-tree nodes (And/Or/Not/Leaf).

    Every node serializes to a ``{"kind": ...}`` dict and is reconstructable
    via ``from_dict``. The discriminating field is ``kind``.
    """

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def from_dict(data: dict[str, Any]) -> TriggerNode:
        kind = _normalize_trigger_kind(str(data.get("kind", "")))
        if kind == "and":
            return And.from_dict(data)
        if kind == "or":
            return Or.from_dict(data)
        if kind == "not":
            return Not.from_dict(data)
        if kind == "leaf":
            return Leaf.from_dict(data)
        raise ValueError(f"Unknown trigger node kind: {kind!r}")


@dataclass
class And(TriggerNode):
    children: list[TriggerNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "and", "children": [c.to_dict() for c in self.children]}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> And:
        children = [TriggerNode.from_dict(c) for c in data.get("children", []) if isinstance(c, dict)]
        return And(children=children)


@dataclass
class Or(TriggerNode):
    children: list[TriggerNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "or", "children": [c.to_dict() for c in self.children]}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Or:
        children = [TriggerNode.from_dict(c) for c in data.get("children", []) if isinstance(c, dict)]
        return Or(children=children)


@dataclass
class Not(TriggerNode):
    child: TriggerNode | None = None

    def to_dict(self) -> dict[str, Any]:
        child = self.child.to_dict() if self.child is not None else None
        return {"kind": "not", "child": child}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Not:
        raw = data.get("child")
        child = TriggerNode.from_dict(raw) if isinstance(raw, dict) else None
        return Not(child=child)


@dataclass
class Leaf(TriggerNode):
    condition: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "leaf", "condition": dict(self.condition)}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Leaf:
        condition = data.get("condition", {})
        if not isinstance(condition, dict):
            condition = {}
        return Leaf(condition=dict(condition))


@dataclass
class ReactionAstNode:
    """Base dataclass for reaction-AST nodes (Seq/If/Switch/ReactionNode)."""

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ReactionAstNode:
        kind = str(data.get("kind", ""))
        if kind == "seq":
            return Seq.from_dict(data)
        if kind == "if":
            return If.from_dict(data)
        if kind == "switch":
            return Switch.from_dict(data)
        if kind == "reaction":
            return ReactionNode.from_dict(data)
        raise ValueError(f"Unknown reaction node kind: {kind!r}")


@dataclass
class Seq(ReactionAstNode):
    children: list[ReactionAstNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "seq", "children": [c.to_dict() for c in self.children]}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Seq:
        children = [ReactionAstNode.from_dict(c) for c in data.get("children", []) if isinstance(c, dict)]
        return Seq(children=children)


@dataclass
class If(ReactionAstNode):
    when: TriggerNode | None = None
    then: ReactionAstNode | None = None
    else_: ReactionAstNode | None = None

    def to_dict(self) -> dict[str, Any]:
        when = self.when.to_dict() if self.when is not None else None
        then = self.then.to_dict() if self.then is not None else None
        else_node = self.else_.to_dict() if self.else_ is not None else None
        return {"kind": "if", "when": when, "then": then, "else": else_node}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> If:
        raw_when = data.get("when")
        when = TriggerNode.from_dict(raw_when) if isinstance(raw_when, dict) else None
        raw_then = data.get("then")
        then = ReactionAstNode.from_dict(raw_then) if isinstance(raw_then, dict) else None
        raw_else = data.get("else")
        else_node = ReactionAstNode.from_dict(raw_else) if isinstance(raw_else, dict) else None
        return If(when=when, then=then, else_=else_node)


@dataclass
class SwitchCase:
    equals: Any = None
    then: ReactionAstNode | None = None

    def to_dict(self) -> dict[str, Any]:
        then = self.then.to_dict() if self.then is not None else None
        return {"equals": self.equals, "then": then}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> SwitchCase:
        then = ReactionAstNode.from_dict(data["then"]) if isinstance(data.get("then"), dict) else None
        return SwitchCase(equals=data.get("equals"), then=then)


@dataclass
class Switch(ReactionAstNode):
    on: str = ""
    cases: list[SwitchCase] = field(default_factory=list)
    default: ReactionAstNode | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "switch",
            "on": self.on,
            "cases": [c.to_dict() for c in self.cases],
            "default": self.default.to_dict() if self.default is not None else None,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Switch:
        on = data.get("on", "")
        cases = [SwitchCase.from_dict(c) for c in data.get("cases", []) if isinstance(c, dict)]
        raw_default = data.get("default")
        default = ReactionAstNode.from_dict(raw_default) if isinstance(raw_default, dict) else None
        return Switch(on=str(on), cases=cases, default=default)


@dataclass
class ReactionNode(ReactionAstNode):
    reaction: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "reaction", "reaction": dict(self.reaction)}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ReactionNode:
        reaction = data.get("reaction", {})
        if not isinstance(reaction, dict):
            reaction = {}
        return ReactionNode(reaction=dict(reaction))


_KIND_MAP = {
    "and": And,
    "or": Or,
    "not": Not,
    "leaf": Leaf,
    "seq": Seq,
    "if": If,
    "switch": Switch,
    "reaction": ReactionNode,
}
