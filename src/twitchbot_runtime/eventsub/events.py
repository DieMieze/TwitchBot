from __future__ import annotations

from typing import Any


def normalize_event(subscription_type: str, event_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """
    @brief Map an EventSub subscription type + event payload to a runtime pair.

    Translates a Twitch EventSub ``subscription.type`` and its ``event``
    payload into the ``(event_name, payload)`` pair consumed by
    ``TwitchBot.handle_event``. Known subscription types are normalized to
    runtime event names; unknown types fall back to ``eventsub.<type>``.

    @param subscription_type: EventSub subscription type string (e.g.
        "channel.chat.message", "channel.follow").
    @param event_payload: the raw ``event`` object delivered by EventSub.
    @return: a ``(event_name, payload)`` tuple in the runtime format.
    """
    if subscription_type == "channel.chat.message":
        return _normalize_chat_message(event_payload)
    if subscription_type == "channel.channel_points_custom_reward_redemption.add":
        return _normalize_redemption(event_payload)
    if subscription_type == "channel.follow":
        return "event.follow", {"username": _user_login(event_payload, "user_name")}
    if subscription_type == "channel.subscribe":
        return "event.sub", {"username": _user_login(event_payload, "user_name"), "gif_id": "sub"}
    if subscription_type == "channel.cheer":
        return "event.cheer", {"username": _user_login(event_payload, "user_name"), "bits": event_payload.get("bits", 0)}
    if subscription_type == "channel.raid":
        return "event.raid", {"username": _user_login(event_payload, "from_broadcaster_user_name"), "viewers": event_payload.get("viewers", 0)}
    return f"eventsub.{subscription_type}", dict(event_payload)


def _normalize_chat_message(event_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """
    @brief Normalize a "channel.chat.message" EventSub payload.

    Extracts the message text, chatter/broadcaster logins, badge-derived
    roles, and the new-chatter flag into a runtime "chat.message" payload.

    @param event_payload: the raw ``event`` object for a chat message.
    @return: a ``("chat.message", payload)`` tuple with keys message,
        username, channel, broadcaster_id, reward_id, is_new_chatter,
        roles, badges.
    """
    message_text = ""
    fragments = event_payload.get("message", {}).get("text")
    if isinstance(fragments, str):
        message_text = fragments
    elif isinstance(event_payload.get("message", {}).get("text"), str):
        message_text = event_payload["message"]["text"]

    reward_id = ""
    badge_ids: list[str] = []
    badges = event_payload.get("badges")
    if isinstance(badges, list):
        for badge in badges:
            if isinstance(badge, dict):
                badge_id = badge.get("id")
                if isinstance(badge_id, str):
                    badge_ids.append(badge_id)

    is_new_chatter = bool(event_payload.get("chatter_is_new", False))

    payload = {
        "message": message_text,
        "username": _user_login(event_payload, "chatter_user_name"),
        "channel": _user_login(event_payload, "broadcaster_user_login"),
        "broadcaster_id": _str_field(event_payload, "broadcaster_user_id"),
        "reward_id": reward_id,
        "is_new_chatter": is_new_chatter,
        "roles": _roles_from_badges(badge_ids),
        "badges": badge_ids,
    }
    return "chat.message", payload


_BADGE_ROLE_MAP = {
    "moderator": "mod",
    "broadcaster": "broadcaster",
    "vip": "vip",
    "subscriber": "subscriber",
}


def _roles_from_badges(badge_ids: list[str]) -> list[str]:
    """
    @brief Map Twitch badge ids to runtime role names.

    Translates known badge ids (moderator, broadcaster, vip, subscriber) into the
    corresponding role strings, preserving order and de-duplicating.

    @param badge_ids: list of badge id strings from the chat payload.
    @return: ordered, de-duplicated list of role strings ("mod",
        "broadcaster", "vip", "subscriber").
    """
    roles: list[str] = []
    for badge_id in badge_ids:
        role = _BADGE_ROLE_MAP.get(badge_id)
        if role is not None and role not in roles:
            roles.append(role)
    return roles


def _normalize_redemption(event_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """
    @brief Normalize a channel point redemption EventSub payload.

    Extracts the reward id, redeeming user, and broadcaster id into a
    runtime "channel_points.redemption" payload.

    @param event_payload: the raw ``event`` object for a redemption.
    @return: a ``("channel_points.redemption", payload)`` tuple with keys
        reward_id, username, broadcaster_id.
    """
    reward = event_payload.get("reward") or {}
    return "channel_points.redemption", {
        "reward_id": reward.get("id", ""),
        "username": _user_login(event_payload, "user_name"),
        "broadcaster_id": _str_field(event_payload, "broadcaster_user_id"),
    }


def _user_login(payload: dict[str, Any], key: str) -> str:
    """
    @brief Safely extract a string user-login field from a payload.

    Returns the value at ``key`` when it is a string, otherwise an empty
    string, so callers never receive None for a username/login.

    @param payload: the raw event payload dict.
    @param key: the dict key holding the user login/name string.
    @return: the login string, or "" when missing/not a string.
    """
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _str_field(payload: dict[str, Any], key: str) -> str:
    """
    @brief Safely extract a string field from a payload.

    Returns the value at ``key`` when it is a string, otherwise an empty
    string, used for ids and other scalar text fields.

    @param payload: the raw event payload dict.
    @param key: the dict key holding the string field.
    @return: the field value, or "" when missing/not a string.
    """
    value = payload.get(key)
    return value if isinstance(value, str) else ""
