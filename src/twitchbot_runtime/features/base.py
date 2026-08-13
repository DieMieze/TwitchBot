from __future__ import annotations

from typing import Any


class BaseFeature:
    """Base class for lightweight runtime features."""

    def __init__(self, enabled: bool = False, name: str | None = None) -> None:
        self.enabled = enabled
        self.name = name or self.__class__.__name__.lower()

    def handles_event(self, event_name: str) -> bool:
        """
        @brief Decide whether this feature wants to react to ``event_name``.

        Returns ``False`` by default, i.e. the feature handles NO event.
        Subclasses MUST override this and return ``True`` for every event
        name they want to receive; otherwise :class:`FeatureManager` silently
        skips the feature and the event is never dispatched to ``handle``.
        The established convention is ``return event_name in {...}`` listing
        the handled names explicitly.

        @param event_name: runtime event name to check.
        @return: ``True`` when this feature should handle the event.
        """
        return False

    def handle(
        self, event_name: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """
        @brief React to ``event_name`` and return reactions (or ``None``).

        Only invoked by :class:`FeatureManager` when :meth:`handles_event`
        returned ``True``. Subclasses override this to produce reactions;
        the default is a no-op returning ``None``.

        @param event_name: runtime event name being handled.
        @param payload: event payload dict, or ``None`` (treated as empty).
        @return: a reaction dict, a list of reaction dicts, or ``None``.
        """
        return None
