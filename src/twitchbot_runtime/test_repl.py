from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .bot import TwitchBot


class ReplSession:
    """Interactive REPL for test mode: dispatch typed events to the bot.

    Used by ``python -m twitchbot_runtime --mode test``. Supports ``help``,
    ``list`` (print configured triggers), ``quit``/``exit``, and arbitrary
    ``<event_name> <json_payload>`` lines forwarded to :meth:`TwitchBot.handle_event`.
    """

    def __init__(self, bot: TwitchBot) -> None:
        """
        @brief Construct a ReplSession bound to a bot.

        @param bot: the TwitchBot events are dispatched to.
        @return: None
        """
        self.bot = bot

    def run(self) -> None:
        """
        @brief Run the interactive read-eval-print loop until quit/EOF.

        @return: None
        """
        print("Test REPL. Type 'help' for commands.")
        while True:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            command = line.split(" ", 1)[0]
            if command == "help":
                print("Commands: help, list, quit/exit, <event_name> <json_payload>")
            elif command == "list":
                print(json.dumps(self.bot.trigger_resolver.list_triggers(), ensure_ascii=False, indent=2))
            elif command in ("quit", "exit"):
                break
            else:
                self._dispatch(line)

    def _dispatch(self, line: str) -> None:
        """
        @brief Parse a ``<event_name> [json_payload]`` line and dispatch it.

        The optional payload must be a JSON object; parse errors are reported
        and the line is dropped. The produced reaction results are printed.

        @param line: the raw REPL line (event name + optional JSON payload).
        @return: None
        """
        if " " in line:
            event_name, rest = line.split(" ", 1)
        else:
            event_name, rest = line, ""
        payload: dict[str, Any] = {}
        if rest.strip():
            try:
                parsed = json.loads(rest)
                if isinstance(parsed, dict):
                    payload = parsed
                else:
                    print("Payload must be a JSON object.")
                    return
            except json.JSONDecodeError as exc:
                print(f"JSON parse error: {exc}")
                return
        reactions = self.bot.handle_event(event_name, payload)
        print(json.dumps(reactions, ensure_ascii=False))


def replay_file(bot: TwitchBot, path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    results: list[dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            event = record.get("event", "")
            payload = record.get("payload", {})
            results.extend(bot.handle_event(event, payload))
    return results
