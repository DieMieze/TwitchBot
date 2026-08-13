from __future__ import annotations

from typing import Any

from .base import BaseFeature


class OverlayFeature(BaseFeature):
    """Feature that handles overlay-style events.

    Test-only hook: this feature reacts solely to the synthetic
    ``event.test`` event, which is NEVER produced in production. EventSub
    events are normalized (see ``eventsub/events.py``) to names like
    ``chat.message``, ``event.follow``, ``event.sub`` … and the timer
    scheduler emits ``timer.tick`` — none of them is ``event.test``. The
    only callers of ``handle_event("event.test", ...)`` are the test suite
    and the test REPL/replay, where it drives an ``overlay_text`` reaction
    through the full pipeline without a real Twitch event.

    In production, ``overlay_text`` reactions are produced by trigger
    entries in ``settings.json`` (matched by ``TriggerResolver``) and
    executed by ``ReactionEngine``, NOT by this feature. This feature
    therefore stays inert in production even when ``features.overlay.enabled``
    is true.
    """

    def __init__(self, enabled: bool = False) -> None:
        super().__init__(enabled=enabled, name='overlay')

    def handles_event(self, event_name: str) -> bool:
        return event_name == 'event.test'

    def handle(self, event_name: str, payload: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
        payload = payload or {}
        return [{'type': 'overlay_text', 'text': payload.get('message', '')}]
