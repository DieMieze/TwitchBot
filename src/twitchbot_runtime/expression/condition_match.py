from __future__ import annotations

from collections.abc import Callable
from typing import Any

_BADGE_ROLE_MAP = {
    "moderator": "mod",
    "broadcaster": "broadcaster",
    "vip": "vip",
    "subscriber": "subscriber",
}


def inject_command_args(payload: dict[str, Any], message: str, command: str) -> None:
    """Extract command arguments from ``message`` into ``payload["args"]``.

    Splits the message remainder after the command prefix into whitespace-
    separated tokens. Does nothing when ``args`` is already present.
    """
    if "args" in payload:
        return
    stripped = message.strip()
    command_stripped = command.strip()
    if stripped.lower().startswith(command_stripped.lower()):
        remainder = stripped[len(command_stripped):]
    else:
        remainder = stripped
    args = remainder.split() if remainder.strip() else []
    payload["args"] = args


def match_event_condition(
    condition: dict[str, Any],
    event_name: str,
    payload: dict[str, Any],
    trigger_name: str,
    *,
    time_provider: Callable[[], float],
    last_trigger_times: dict[str, float],
    chatter_tracker: Any = None,
) -> bool:
    """Evaluate a single event-type condition against the event and payload.

    Supports the event types ``command``, ``time``, ``channel_point_reward``,
    ``first_time_chatter`` (Twitch ``chatter_is_new`` flag),
    ``new_chatter`` (inactivity window via an injected ``chatter_tracker``),
    ``follow``, ``sub``, ``cheer`` (with ``min_bits``) and ``raid`` (with
    ``min_viewers``). ``role`` checks the payload roles via
    :func:`matches_roles` (Broadcaster override applies) and is intended for
    ``if.when`` per-case role gating inside the reaction tree (it is also
    valid in a trigger ``when`` tree). Returns ``False`` for unknown types.

    ``chatter_tracker`` is optional: when ``None``, the ``new_chatter`` window
    cannot be evaluated and the leaf returns ``False`` (safe default — no false
    positives). ``first_time_chatter`` does not need the tracker.
    """
    cond_type = condition.get("type")

    if cond_type == "command":
        message = payload.get("message", "")
        command = condition.get("command", "")
        if not command:
            return False
        if not message.strip().lower().startswith(command.strip().lower()):
            return False
        inject_command_args(payload, message, command)
        return True

    if cond_type == "time":
        interval_minutes = condition.get("interval_minutes")
        if interval_minutes is None:
            return False
        interval_seconds = interval_minutes * 60
        last = last_trigger_times.get(trigger_name, 0)
        if last == 0:
            return True
        return (time_provider() - last) >= interval_seconds

    if cond_type == "channel_point_reward":
        return payload.get("reward_id") == condition.get("reward_id")

    if cond_type == "first_time_chatter":
        return payload.get("is_new_chatter") is True

    if cond_type == "new_chatter":
        if chatter_tracker is None:
            return False
        window = condition.get("time")
        if window is None or window <= 0:
            return False
        channel = payload.get("channel", "") or ""
        username = payload.get("username", payload.get("user_name", "")) or ""
        if not channel or not username:
            return False
        return chatter_tracker.is_new(channel, username, float(window), time_provider())

    if cond_type == "follow":
        return event_name == "event.follow"

    if cond_type == "sub":
        return event_name == "event.sub"

    if cond_type == "cheer":
        if event_name != "event.cheer":
            return False
        min_bits = condition.get("min_bits")
        if min_bits is None or min_bits <= 0:
            return True
        bits = payload.get("bits", 0)
        try:
            return int(bits) >= int(min_bits)
        except (TypeError, ValueError):
            return False

    if cond_type == "raid":
        if event_name != "event.raid":
            return False
        min_viewers = condition.get("min_viewers")
        if min_viewers is None or min_viewers <= 0:
            return True
        viewers = payload.get("viewers", 0)
        try:
            return int(viewers) >= int(min_viewers)
        except (TypeError, ValueError):
            return False

    if cond_type == "role":
        required = condition.get("roles")
        if not required:
            return True
        if isinstance(required, str):
            required = [required]
        payload_roles_list = payload_roles(payload)
        return matches_roles({"roles": required}, payload_roles_list)

    return False


def payload_roles(payload: dict[str, Any]) -> list[str]:
    """Derive a list of role names from the event payload (roles or badges)."""
    roles = payload.get("roles")
    if isinstance(roles, list):
        return [str(role) for role in roles]
    if isinstance(roles, str) and roles:
        return [roles]
    badges = payload.get("badges")
    if isinstance(badges, list):
        mapped: list[str] = []
        for badge in badges:
            badge_id = badge if isinstance(badge, str) else (badge.get("id") if isinstance(badge, dict) else None)
            if not isinstance(badge_id, str):
                continue
            role = _BADGE_ROLE_MAP.get(badge_id, badge_id)
            if role not in mapped:
                mapped.append(role)
        return mapped
    return []


def matches_roles(trigger: dict[str, Any], payload_roles_list: list[str]) -> bool:
    """Check whether the payload roles satisfy a trigger's role requirement."""
    required = trigger.get("roles")
    if not required:
        return True
    if not isinstance(required, list):
        required = [required]
    if "everyone" in required:
        return True
    if not payload_roles_list:
        return False
    if "broadcaster" in payload_roles_list:
        return True
    return any(role in payload_roles_list for role in required)
