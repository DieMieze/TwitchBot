from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from twitchbot_runtime.config_schema import build_config_schema_message
from twitchbot_runtime.logger import Logger, get_logger

MessageHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


class WebsocketHandler:
    """Minimal websocket handler that serves the generated config schema.

    The handler mirrors the message-parsing style used by the overlay manager
    (action/data JSON envelopes) without depending on an existing websocket
    implementation. It is intentionally transport-agnostic: callers wire the
    ``handle_message`` coroutine to whatever websocket server they run.
    """

    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger if logger is not None else get_logger(__name__)
        self._handlers: dict[str, MessageHandler] = {
            "config_schema": self._handle_config_schema,
        }

    def register_handler(self, message_type: str, handler: MessageHandler) -> None:
        self._handlers[message_type] = handler

    async def handle_message(self, raw: str | bytes | dict[str, Any]) -> dict[str, Any] | None:
        message = self._parse(raw)
        message_type = message.get("type")
        if not message_type:
            return {"type": "error", "error": "Missing 'type' field in message"}

        handler = self._handlers.get(message_type)
        if handler is None:
            return {
                "type": "error",
                "error": f"Unknown message type: {message_type}",
            }

        try:
            return await handler(message)
        except Exception as exc:
            self._logger.exception("Error handling websocket message: %s", message)
            return {"type": "error", "error": str(exc)}

    async def _handle_config_schema(self, _message: dict[str, Any]) -> dict[str, Any]:
        return build_config_schema_message()

    @staticmethod
    def _parse(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def build_config_schema_payload(self) -> dict[str, Any]:
        return build_config_schema_message()


async def _send_config_schema_example() -> dict[str, Any]:
    handler = WebsocketHandler()
    result = await handler.handle_message({"type": "config_schema"})
    assert isinstance(result, dict)
    return result


if __name__ == "__main__":
    result = asyncio.run(_send_config_schema_example())
    print(json.dumps(result, indent=2, ensure_ascii=False))
