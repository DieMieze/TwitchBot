from __future__ import annotations

from collections import defaultdict
from typing import Any


class ChatterTracker:
    """In-memory per-channel record of when each chatter last spoke.

    The runtime records every ``chat.message`` event via :meth:`record` so the
    ``new_chatter`` (inactivity-window) trigger can answer "has this chatter
    been silent for at least N seconds?". State is **in-memory only**: a bot
    restart loses all history, so the first message of a chatter after a
    restart counts as "new" for any window. Persistence is out of scope for V1.
    """

    # --- Member variables ---
    _last_seen: dict[str, dict[str, float]]  # channel -> {username -> last_seen_timestamp}

    def __init__(self) -> None:
        """
        @brief Construct an empty in-memory ChatterTracker.

        @return: None
        """
        self._last_seen: dict[str, dict[str, float]] = defaultdict(dict)

    def record(self, channel: str, username: str, timestamp: float) -> None:
        """
        @brief Record that a chatter spoke in a channel at the given time.

        Overwrites any previous last-seen timestamp for the (channel, username)
        pair. Call this for EVERY chat.message event, before trigger resolution,
        so the window evaluation sees the latest activity.

        @param channel: the channel name (runtime payload ``channel``).
        @param username: the chatter login (runtime payload ``username``).
        @param timestamp: the event time in seconds (e.g. time.time()).
        @return: None
        """
        if not channel or not username:
            return
        self._last_seen[channel][username] = timestamp

    def is_new(self, channel: str, username: str, window_seconds: float, now: float) -> bool:
        """
        @brief Return whether a chatter is "new" within an inactivity window.

        True when the chatter has never spoken in the channel (no record) OR
        when the time since their last message is >= ``window_seconds``. False
        when the chatter spoke recently (within the window) or inputs are
        missing.

        @param channel: the channel name.
        @param username: the chatter login.
        @param window_seconds: inactivity window in seconds (must be > 0).
        @param now: the reference time in seconds.
        @return: True when the chatter is considered new for the window.
        """
        if not channel or not username or window_seconds <= 0:
            return False
        last = self._last_seen.get(channel, {}).get(username)
        if last is None:
            return True
        return (now - last) >= window_seconds

    def snapshot(self) -> dict[str, Any]:
        """
        @brief Return a plain-copy snapshot of the tracked last-seen state.

        Useful for tests and debugging; mutating the returned dict does not
        affect the tracker.

        @return: a nested dict {channel: {username: last_seen_timestamp}}.
        """
        return {channel: dict(users) for channel, users in self._last_seen.items()}


__all__ = ["ChatterTracker"]
