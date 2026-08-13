from __future__ import annotations

import json
import time
from pathlib import Path


class SilentEventCollector:
    """Captures inbound events to a JSONL file (per-type cap) in silent mode.

    Each event is appended as a JSON line with ``event``, ``payload`` and
    ``timestamp``. Per-type collection is capped at ``max_per_type`` so a chatty
    event type cannot starve the file; once the cap is reached further events
    of that type are dropped.
    """

    def __init__(
        self,
        store_path: str | Path = "output/silent_events.jsonl",
        max_per_type: int = 50,
    ) -> None:
        """
        @brief Construct a collector writing to a JSONL file.

        @param store_path: path to the JSONL capture file; parent dirs are
            created on construction.
        @param max_per_type: maximum number of events kept per event type
            (older ones are NOT evicted — once the cap is hit, new events of
            that type are dropped).
        @return: None
        """
        self.store_path = Path(store_path)
        self.max_per_type = max_per_type
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._counts: dict[str, int] = {}

    def collect(self, event_name: str, payload: dict) -> bool:
        """
        @brief Append an event record to the JSONL file when under the cap.

        @param event_name: runtime event name (e.g. ``chat.message``).
        @param payload: event payload dict.
        @return: True when the record was appended, False when the per-type cap
            was already reached (event dropped).
        """
        if self._counts.get(event_name, 0) >= self.max_per_type:
            return False
        record = {"event": event_name, "payload": payload, "timestamp": time.time()}
        with self.store_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._counts[event_name] = self._counts.get(event_name, 0) + 1
        return True

    def counts(self) -> dict[str, int]:
        """
        @brief Return the per-type collected-event counts so far.

        @return: a dict mapping event name to the number of appended records.
        """
        return self._counts
