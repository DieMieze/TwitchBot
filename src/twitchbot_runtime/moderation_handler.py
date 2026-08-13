from __future__ import annotations

from typing import Any

from .logger import Logger, get_logger
from .mode import Mode


class ModerationHandler:
    """Executes moderation actions (ban/timeout/delete_message/purge).

    In production mode, real Twitch API calls are stubbed with logging
    (actual API integration is out of scope). In silent/test mode, actions
    are nooped and only logged.
    """

    # --- Member variables ---
    mode: Mode  # execution mode (gate for real API vs noop)
    logger: Logger  # logger instance (defaults to module logger)
    actor: Any  # optional ModerationActor for real Helix dispatch (None = stub/noop)

    def __init__(
        self,
        mode: Mode | str = Mode.PRODUCTION,
        logger: Logger | None = None,
        actor: Any | None = None,
    ) -> None:
        self.mode = mode if isinstance(mode, Mode) else Mode.from_string(str(mode))
        self.logger = logger if logger is not None else get_logger(__name__)
        self.actor = actor

    def handle(self, action: str, payload: dict) -> dict:
        """
        @brief Execute a moderation action for the given payload.

        Dispatches ban/timeout/delete_message/purge actions. In silent or
        test mode the call is nooped and only logged. In production mode it
        delegates to the injected actor when present, otherwise logs a stub
        result.

        @param action: moderation action name; one of "ban", "timeout",
            "delete_message", "purge".
        @param payload: dictionary describing the action target and options
            (keys: target, duration, reason, message_id).
        @return: result dictionary with at least "status" and "action" keys;
            "unknown_action" for unsupported actions, "noop" in silent/test
            mode, the actor/stub result otherwise.
        """
        target = payload.get("target")
        duration = payload.get("duration")
        reason = payload.get("reason")
        message_id = payload.get("message_id")

        if action not in {"ban", "timeout", "delete_message", "purge"}:
            self.logger.info("Unknown moderation action: %s", action)
            return {"status": "unknown_action", "action": action}

        if self.mode in {Mode.SILENT, Mode.TEST}:
            self.logger.info("Moderation noop (%s mode): action=%s target=%s", self.mode.value, action, target)
            return {"status": "noop", "action": action, "target": target}

        if self.actor is not None:
            return self._dispatch_to_actor(action, payload)

        self.logger.info(
            "Moderation stub (production): action=%s target=%s duration=%s reason=%s message_id=%s",
            action,
            target,
            duration,
            reason,
            message_id,
        )
        return {
            "status": "stub_executed",
            "action": action,
            "target": target,
            "duration": duration,
            "reason": reason,
            "message_id": message_id,
        }

    def _dispatch_to_actor(self, action: str, payload: dict) -> dict:
        """
        @brief Forward a moderation action to the injected actor.

        Maps the action name to the matching ModerationActor method
        (ban/timeout/delete_message/purge) and returns its result.

        @param action: moderation action name; one of "ban", "timeout",
            "delete_message", "purge".
        @param payload: dictionary describing the action target and options
            (keys: target, duration, reason, message_id).
        @return: the actor's result dictionary, or {"status": "unknown_action",
            "action": action} for unsupported actions.
        """
        target = payload.get("target", "")
        duration = payload.get("duration")
        reason = payload.get("reason")
        message_id = payload.get("message_id")

        if action == "ban":
            return self.actor.ban(target, reason=reason)
        if action == "timeout":
            duration_value = int(duration) if duration is not None else 0
            return self.actor.timeout(target, duration_value, reason=reason)
        if action == "delete_message":
            return self.actor.delete_message(message_id or target or "")
        if action == "purge":
            return self.actor.purge(target)
        return {"status": "unknown_action", "action": action}
