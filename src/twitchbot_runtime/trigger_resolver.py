from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from .expression.condition_match import matches_roles as _matches_roles_impl
from .expression.condition_match import payload_roles as _payload_roles_impl
from .expression.evaluator import evaluate_when, walk_trigger_leaves
from .expression.nodes import And, Leaf, TriggerNode

_CONTEXT_PLACEHOLDER = re.compile(r"\{(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)\}")
_ARGS_PLACEHOLDER = re.compile(r"\{args\[(?P<index>\d+)\]\}")
_TARGET_PLACEHOLDER = re.compile(r"\{target\}")


class TriggerResolver:
    """Resolves triggers against an incoming event and payload.

    Reads the recursive ``trigger["when"]`` tree (AND/OR/NOT/leaf) and
    evaluates it via :func:`expression.evaluator.evaluate_when`. Legacy
    ``trigger["triggers"]`` and ``conditions:{all,any}`` formats are no longer
    supported.
    """

    # --- Member variables ---
    triggers: list[dict[str, Any]]  # configured trigger entries to match against events
    _time_provider: Callable[[], float]  # injectable clock returning the current time in seconds
    _last_trigger_times: dict[str, float]  # per-trigger-name timestamps of the last successful match
    _counter_handler: Any  # optional counter handler exposing resolve_placeholders (for compare {counter:...})
    _chatter_tracker: Any  # optional ChatterTracker for new_chatter (inactivity window) leaves
    _resolve_placeholder: Callable[[str], str]  # placeholder resolver used by compare leaves

    def __init__(
        self,
        triggers: list[dict[str, Any]] | None = None,
        time_provider: Callable[[], float] | None = None,
        counter_handler: Any = None,
        chatter_tracker: Any = None,
    ) -> None:
        """
        @brief Construct a TriggerResolver with a trigger list, optional clock, counter and chatter tracker.

        @param triggers: list of trigger dicts in Runtime format (``when`` tree
            + ``reactions`` root); defaults to an empty list when ``None``.
        @param time_provider: callable returning the current time in seconds
            (used for ``time`` trigger cooldowns); defaults to ``time.time``.
        @param counter_handler: optional counter handler exposing
            ``resolve_placeholders(message)`` so that ``compare`` leaves can
            resolve ``{counter:...}`` placeholders. When ``None``, ``{counter:...}``
            tokens are left unresolved (compare compares the raw string).
        @param chatter_tracker: optional ChatterTracker exposing
            ``is_new(channel, username, window, now)`` so that ``new_chatter``
            (inactivity-window) leaves can be evaluated. When ``None``, the
            ``new_chatter`` leaf returns ``False`` (no false positives).
        @return: None
        """
        self.triggers: list[dict[str, Any]] = triggers or []
        self._time_provider = time_provider or time.time
        self._last_trigger_times: dict[str, float] = {}
        self._counter_handler = counter_handler
        self._chatter_tracker = chatter_tracker
        self._resolve_placeholder = self._build_resolve_placeholder(counter_handler)

    @staticmethod
    def _build_resolve_placeholder(counter_handler: Any) -> Callable[[str], str]:
        resolve_counter = getattr(counter_handler, "resolve_placeholders", None)
        if callable(resolve_counter):
            return resolve_counter
        return lambda text: text

    def resolve(self, event_name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """
        @brief Resolve all matching triggers for an event and collect their reactions.

        Iterates over the configured triggers, filtering by event name, optional
        ``trigger_name`` selector in the payload and role requirements, then
        evaluates the ``when`` tree. Matching triggers contribute their
        ``reactions`` root node (un-evaluated — the engine evaluates the AST)
        to the returned list, and their last-match timestamp is updated for
        ``time`` trigger cooldown tracking.

        @param event_name: the runtime event name (e.g. ``event.follow``).
        @param payload: event payload dict, may carry ``trigger_name``,
            ``roles``/``badges``, ``message``, ``args``, etc.
        @return: list of reaction root dicts aggregated from all matching triggers.
        """
        reactions: list[dict[str, Any]] = []
        selected_trigger_name = payload.get("trigger_name")
        payload_roles = _payload_roles_impl(payload)

        for trigger in self.triggers:
            if not isinstance(trigger, dict):
                continue
            name = trigger.get("name", "")

            if trigger.get("event") and trigger.get("event") != event_name:
                continue
            if selected_trigger_name and name != selected_trigger_name:
                continue

            if not _matches_roles_impl(trigger, payload_roles):
                continue

            when_node = trigger.get("when")
            if not self._matches_when(trigger, when_node, event_name, payload, name):
                continue

            reactions_root = trigger.get("reactions")
            if isinstance(reactions_root, dict):
                reactions.append(reactions_root)

            self._last_trigger_times[name] = self._time_provider()

        return reactions

    def _matches_when(
        self,
        trigger: dict[str, Any],
        when_node: Any,
        event_name: str,
        payload: dict[str, Any],
        name: str,
    ) -> bool:
        """Evaluate the trigger's ``when`` tree; default to a matching and-node."""
        if when_node is None:
            return True
        return evaluate_when(
            when_node,
            event_name,
            payload,
            match_condition=self._match_condition,
            resolve_placeholder=self._build_payload_resolver(event_name, payload),
            on_time_match=self._record_time_match,
            trigger_name=name,
        )

    def _build_payload_resolver(self, event_name: str, payload: dict[str, Any]) -> Callable[[str], str]:
        """Build a placeholder resolver bound to the current event/payload.

        Resolution order: counter (injected handler) → args[N] → target →
        context keys from the payload (event_name, username, channel, ...).
        Mirrors :class:`ReactionEngine._resolve_placeholders` so resolver-side
        and engine-side ``compare`` leaves behave identically.
        """
        counter_resolver = self._resolve_placeholder

        def _resolve(text: str) -> str:
            if not text:
                return text
            text = counter_resolver(text)
            args = payload.get("args")
            if isinstance(args, list) and args:
                def _replace_args(match: re.Match[str]) -> str:
                    index = int(match.group("index"))
                    if index < 0 or index >= len(args):
                        return match.group(0)
                    return str(args[index])

                text = _ARGS_PLACEHOLDER.sub(_replace_args, text)

                def _replace_target(match: re.Match[str]) -> str:
                    return str(args[0])

                text = _TARGET_PLACEHOLDER.sub(_replace_target, text)

            def _replace_context(match: re.Match[str]) -> str:
                key = match.group("key")
                if key == "event_name":
                    value: Any = event_name
                elif key == "username":
                    value = payload.get("username", payload.get("user_name", ""))
                else:
                    value = payload.get(key)
                if value is None:
                    return match.group(0)
                return str(value)

            return _CONTEXT_PLACEHOLDER.sub(_replace_context, text)

        return _resolve

    def _match_condition(
        self,
        condition: dict[str, Any],
        event_name: str,
        payload: dict[str, Any],
        trigger_name: str,
    ) -> bool:
        """Delegate an event-type leaf to the shared matcher bound to this resolver's clock."""
        from .expression.condition_match import match_event_condition

        return match_event_condition(
            condition,
            event_name,
            payload,
            trigger_name,
            time_provider=self._time_provider,
            last_trigger_times=self._last_trigger_times,
            chatter_tracker=self._chatter_tracker,
        )

    def _record_time_match(self, trigger_name: str) -> None:
        """No-op placeholder: the cooldown timestamp is updated post-match in resolve()."""
        return None

    def list_triggers(self) -> list[dict[str, Any]]:
        """
        @brief Produce a lightweight summary of every configured trigger.

        @return: list of dicts with ``name``, ``event`` and ``conditions_count``
            (the number of leaf conditions in the ``when`` tree) for each trigger.
        """
        summaries: list[dict[str, Any]] = []
        for trigger in self.triggers:
            if not isinstance(trigger, dict):
                continue
            when_node = trigger.get("when")
            leaves = walk_trigger_leaves(when_node) if when_node is not None else []
            summaries.append(
                {
                    "name": trigger.get("name", ""),
                    "event": trigger.get("event"),
                    "conditions_count": len(leaves),
                }
            )
        return summaries


def default_when_tree() -> dict[str, Any]:
    """Return the default empty ``when`` tree used when a trigger omits ``when``."""
    return And(children=[]).to_dict()


def default_reaction_root() -> dict[str, Any]:
    """Return the default empty ``seq`` reaction root."""
    return {"kind": "seq", "children": []}


def default_leaf(condition_type: str = "command", **fields: Any) -> dict[str, Any]:
    """Build a leaf ``when`` node dict for a single condition."""
    return Leaf(condition={"type": condition_type, **fields}).to_dict()


def default_and(*leaves: dict[str, Any]) -> dict[str, Any]:
    """Build an ``and`` ``when`` node dict wrapping the given leaf dicts."""
    from .expression.nodes import TriggerNode

    children = [TriggerNode.from_dict(leaf) for leaf in leaves]
    return And(children=children).to_dict()


__all__ = [
    "TriggerResolver",
    "TriggerNode",
    "default_when_tree",
    "default_reaction_root",
    "default_leaf",
    "default_and",
]
