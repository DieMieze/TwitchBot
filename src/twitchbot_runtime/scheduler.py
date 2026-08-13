from __future__ import annotations

import threading
from typing import Any

from .expression.evaluator import walk_trigger_leaves
from .logger import get_logger

logger = get_logger(__name__)


class TimerScheduler:
    """Drives ``time``-based triggers by periodically calling
    ``bot.handle_event("timer.tick", {})``.

    Scans ``settings["triggers"]`` for ``time`` leaves in the ``when`` tree
    and computes the coarsest interval needed. Runs in a daemon thread so it
    never blocks process shutdown.
    """

    MIN_INTERVAL_SECONDS = 1.0
    DEFAULT_INTERVAL_SECONDS = 60.0

    def __init__(self, bot: Any, interval_seconds: float | None = None) -> None:
        """
        @brief Construct a TimerScheduler bound to a bot.

        @param bot: the TwitchBot whose ``handle_event("timer.tick", {})`` is
            called on each tick.
        @param interval_seconds: optional fixed tick interval in seconds;
            when None the interval is computed from the configured ``time``
            triggers (see :meth:`compute_interval`).
        @return: None
        """
        self._bot = bot
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._interval = interval_seconds

    def compute_interval(self) -> float:
        """
        @brief Compute the tick interval in seconds.

        When a fixed interval was supplied it is returned (clamped to the
        minimum). Otherwise scans every configured trigger's ``when`` tree for
        ``time`` leaves and returns the smallest ``interval_minutes * 60``,
        clamped to :attr:`MIN_INTERVAL_SECONDS`. Falls back to
        :attr:`DEFAULT_INTERVAL_SECONDS` when no ``time`` trigger is configured.

        @return: the tick interval in seconds (>= MIN_INTERVAL_SECONDS).
        """
        if self._interval is not None:
            return max(self._interval, self.MIN_INTERVAL_SECONDS)

        min_minutes: float | None = None
        for trigger in self._bot.settings.get("triggers", []) or []:
            if not isinstance(trigger, dict):
                continue
            when_node = trigger.get("when")
            if when_node is None:
                continue
            for condition in walk_trigger_leaves(when_node):
                if condition.get("type") != "time":
                    continue
                interval_minutes = condition.get("interval_minutes")
                if interval_minutes is None:
                    continue
                try:
                    minutes = float(interval_minutes)
                except (TypeError, ValueError):
                    continue
                if minutes <= 0:
                    continue
                if min_minutes is None or minutes < min_minutes:
                    min_minutes = minutes

        if min_minutes is None:
            return self.DEFAULT_INTERVAL_SECONDS

        return max(min_minutes * 60.0, self.MIN_INTERVAL_SECONDS)

    def start(self) -> None:
        """
        @brief Start the periodic tick loop in a daemon thread (no-op if running).

        @return: None
        """
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        interval = self.compute_interval()
        self._thread = threading.Thread(target=self._loop, args=(interval,), daemon=True)
        self._thread.start()
        logger.info("TimerScheduler started (interval=%.2fs)", interval)

    def stop(self) -> None:
        """
        @brief Signal the tick loop to stop and join the daemon thread.

        @return: None
        """
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None

    def _loop(self, interval: float) -> None:
        """
        @brief Daemon loop body: sleep ``interval`` then dispatch a timer.tick.

        Exits cleanly when the stop event is set. Tick dispatch failures are
        logged but do not stop the loop.

        @param interval: sleep duration in seconds between ticks.
        @return: None
        """
        while not self._stop_event.is_set():
            if self._stop_event.wait(interval):
                break
            try:
                self._bot.handle_event("timer.tick", {})
            except Exception:
                logger.exception("TimerScheduler failed to dispatch timer.tick")
