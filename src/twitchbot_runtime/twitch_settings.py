from __future__ import annotations

import os
from pathlib import Path

BOT_REQUIRED_KEYS = ("BOT_CLIENT_ID", "BOT_CLIENT_SECRET", "BOT_USERNAME", "TWITCH_CHANNEL")

BOT_SCOPES = [
    "user:read:chat",
    "user:bot",
    "user:write:chat",
    "moderator:read:followers",
    "moderator:manage:banned_users",
    "moderator:manage:chat_messages",
    "clips:edit",
]

CHANNEL_SCOPES = [
    "channel:bot",
    "channel:read:subscriptions",
    "channel:read:redemptions",
    "bits:read",
]


def _strip_quotes(value: str) -> str:
    """
    @brief Strip a single layer of matching surrounding quotes from a value.

    @param value: raw string possibly wrapped in ``"..."`` or ``'...'``.
    @return: the value with one outer quote pair removed, or the stripped
        value when it is not fully quote-wrapped.
    """
    value = value.strip()
    if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
        return value[1:-1]
    return value


def parse_env_text(text: str) -> dict[str, str]:
    """
    @brief Parse a simple ``KEY=VALUE`` .env document into a dict.

    Ignores blank lines and ``#`` comments at line start. Strips optional
    surrounding quotes from values. No multiline continuation support.

    @param text: full contents of a ``.env`` file as a single string.
    @return: ordered mapping of env keys to their unquoted string values.
    """
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        result[key] = _strip_quotes(value)
    return result


def serialize_env(mapping: dict[str, str]) -> str:
    """
    @brief Serialize a mapping back into a ``KEY=VALUE`` .env document.

    ``None`` values are emitted as empty strings. The output always ends
    with a trailing newline when there is at least one entry.

    @param mapping: ordered mapping of env keys to string values.
    @return: a newline-separated ``KEY=VALUE`` text representation.
    """
    lines: list[str] = []
    for key, value in mapping.items():
        if value is None:
            value = ""
        lines.append(f"{key}={value}")
    return "\n".join(lines) + ("\n" if lines else "")


class TwitchSettings:
    """Wrapper around the project-root ``.env`` file holding Twitch secrets.

    Account secrets (bot + channel OAuth tokens, client id/secret) live in
    ``.env``; only ``twitch.webhook_secret`` stays in ``settings.json``.
    """

    # --- Member variables ---
    env_path: Path  # path to the .env file this wrapper reads/writes
    _values: dict[str, str]  # in-memory cache of parsed KEY=VALUE entries

    def __init__(self, env_path: str | Path | None = None) -> None:
        """
        @brief Construct a settings wrapper around a .env file path.

        Does not read the file yet; call :meth:`reload` (or use
        :meth:`load`) to populate the in-memory values.

        @param env_path: path to the .env file; defaults to ``.env`` in the
            current working directory when ``None``.
        @return: None
        """
        self.env_path = Path(env_path) if env_path is not None else Path(".env")
        self._values: dict[str, str] = {}

    @classmethod
    def load(cls, env_path: str | Path | None = None) -> TwitchSettings:
        """
        @brief Create an instance and immediately load it from disk.

        Convenience factory combining construction with :meth:`reload` so
        callers get a ready-to-use settings object in one call.

        @param env_path: path to the .env file; defaults to ``.env`` when
            ``None``.
        @return: a fully populated :class:`TwitchSettings` instance.
        """
        instance = cls(env_path)
        instance.reload()
        return instance

    def reload(self) -> None:
        """
        @brief Re-read the .env file from disk into the in-memory cache.

        When the file does not exist the cache is reset to an empty dict,
        leaving the wrapper usable without a backing file.

        @return: None
        """
        if self.env_path.exists():
            text = self.env_path.read_text(encoding="utf-8")
            self._values = parse_env_text(text)
        else:
            self._values = {}

    def write_env(self, updates: dict[str, str]) -> None:
        """
        @brief Merge updates into the .env file and persist it.

        Reloads the current on-disk contents first (so external edits are
        preserved), applies the provided key/value pairs, creates parent
        directories as needed, then writes the serialized result.

        @param updates: mapping of keys to new string values; ``None``
            values are skipped, not written.
        @return: None
        """
        self.reload()
        for key, value in updates.items():
            if value is None:
                continue
            self._values[key] = str(value)
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.write_text(serialize_env(self._values), encoding="utf-8")

    def get(self, key: str, default: str = "") -> str:
        """
        @brief Fetch a raw env value by key with a default fallback.

        @param key: env key name to look up.
        @param default: value returned when the key is absent.
        @return: the stored string value, or ``default`` when missing.
        """
        return self._values.get(key, default)

    def _attr(self, key: str) -> str:
        """
        @brief Internal accessor returning an env value or empty string.

        Used by the typed property accessors so they always return a plain
        string instead of raising on missing keys.

        @param key: env key name to look up.
        @return: the stored value, or ``""`` when the key is absent.
        """
        return self._values.get(key, "")

    @property
    def bot_username(self) -> str:
        """
        @brief Bot account login name (``BOT_USERNAME``).

        @return: the bot's username, or ``""`` when unset.
        """
        return self._attr("BOT_USERNAME")

    @property
    def bot_client_id(self) -> str:
        """
        @brief Bot Twitch application client id (``BOT_CLIENT_ID``).

        @return: the bot client id, or ``""`` when unset.
        """
        return self._attr("BOT_CLIENT_ID")

    @property
    def bot_client_secret(self) -> str:
        """
        @brief Bot Twitch application client secret (``BOT_CLIENT_SECRET``).

        @return: the bot client secret, or ``""`` when unset.
        """
        return self._attr("BOT_CLIENT_SECRET")

    @property
    def bot_oauth_token(self) -> str:
        """
        @brief Bot user OAuth access token (``BOT_OAUTH_TOKEN``).

        @return: the bot access token, or ``""`` when unset.
        """
        return self._attr("BOT_OAUTH_TOKEN")

    @property
    def bot_refresh_token(self) -> str:
        """
        @brief Bot OAuth refresh token (``BOT_REFRESH_TOKEN``).

        @return: the bot refresh token, or ``""`` when unset.
        """
        return self._attr("BOT_REFRESH_TOKEN")

    @property
    def bot_channel_id(self) -> str:
        """
        @brief Numeric user id of the bot account (``BOT_CHANNEL_ID``).

        @return: the bot's user id, or ``""`` when unset.
        """
        return self._attr("BOT_CHANNEL_ID")

    @property
    def twitch_channel(self) -> str:
        """
        @brief Target broadcaster login (``TWITCH_CHANNEL``).

        @return: the channel login name, or ``""`` when unset.
        """
        return self._attr("TWITCH_CHANNEL")

    @property
    def twitch_channel_id(self) -> str:
        """
        @brief Numeric user id of the target broadcaster (``TWITCH_CHANNEL_ID``).

        @return: the broadcaster's user id, or ``""`` when unset.
        """
        return self._attr("TWITCH_CHANNEL_ID")

    @property
    def channel_client_id(self) -> str:
        """
        @brief Channel Twitch application client id with bot fallback.

        Returns ``CHANNEL_CLIENT_ID`` when set, otherwise falls back to the
        bot client id so a single app credential can serve both roles.

        @return: the channel client id, falling back to the bot client id.
        """
        return self._attr("CHANNEL_CLIENT_ID") or self.bot_client_id

    @property
    def channel_oauth_token(self) -> str:
        """
        @brief Channel user OAuth access token (``CHANNEL_OAUTH_TOKEN``).

        @return: the channel access token, or ``""`` when unset.
        """
        return self._attr("CHANNEL_OAUTH_TOKEN")

    @property
    def channel_refresh_token(self) -> str:
        """
        @brief Channel OAuth refresh token (``CHANNEL_REFRESH_TOKEN``).

        @return: the channel refresh token, or ``""`` when unset.
        """
        return self._attr("CHANNEL_REFRESH_TOKEN")

    def missing_bot_keys(self) -> list[str]:
        """
        @brief List required bot keys whose values are empty/missing.

        @return: subset of :data:`BOT_REQUIRED_KEYS` that are not set.
        """
        return [key for key in BOT_REQUIRED_KEYS if not self._attr(key)]

    def missing_channel_keys(self) -> list[str]:
        """
        @brief List required channel keys whose values are empty/missing.

        Currently only ``TWITCH_CHANNEL`` is required for the channel side.

        @return: list of missing channel-required keys.
        """
        return [key for key in ("TWITCH_CHANNEL",) if not self._attr(key)]

    def bot_scopes_present(self, scopes: list[str] | None = None) -> list[str]:
        """
        @brief List which requested bot scopes are present in ``BOT_SCOPES``.

        @param scopes: desired scopes; defaults to :data:`BOT_SCOPES` when
            ``None``.
        @return: the subset of requested scopes found in the stored
            ``BOT_SCOPES`` value, preserving the requested order.
        """
        present = self._scopes_list("BOT_SCOPES")
        wanted = scopes if scopes is not None else BOT_SCOPES
        return [scope for scope in wanted if scope in present]

    def bot_scopes_missing(self, scopes: list[str] | None = None) -> list[str]:
        """
        @brief List which requested bot scopes are absent from ``BOT_SCOPES``.

        @param scopes: desired scopes; defaults to :data:`BOT_SCOPES` when
            ``None``.
        @return: the subset of requested scopes not found in the stored
            ``BOT_SCOPES`` value, preserving the requested order.
        """
        present = set(self.bot_scopes_present(scopes))
        wanted = scopes if scopes is not None else BOT_SCOPES
        return [scope for scope in wanted if scope not in present]

    def channel_scopes_present(self, scopes: list[str] | None = None) -> list[str]:
        """
        @brief List which requested channel scopes are present in ``CHANNEL_SCOPES``.

        @param scopes: desired scopes; defaults to :data:`CHANNEL_SCOPES`
            when ``None``.
        @return: the subset of requested scopes found in the stored
            ``CHANNEL_SCOPES`` value, preserving the requested order.
        """
        present = self._scopes_list("CHANNEL_SCOPES")
        wanted = scopes if scopes is not None else CHANNEL_SCOPES
        return [scope for scope in wanted if scope in present]

    def channel_scopes_missing(self, scopes: list[str] | None = None) -> list[str]:
        """
        @brief List which requested channel scopes are absent from ``CHANNEL_SCOPES``.

        @param scopes: desired scopes; defaults to :data:`CHANNEL_SCOPES`
            when ``None``.
        @return: the subset of requested scopes not found in the stored
            ``CHANNEL_SCOPES`` value, preserving the requested order.
        """
        present = set(self.channel_scopes_present(scopes))
        wanted = scopes if scopes is not None else CHANNEL_SCOPES
        return [scope for scope in wanted if scope not in present]

    def _scopes_list(self, key: str) -> list[str]:
        """
        @brief Parse a comma/space-separated scopes env field into a list.

        @param key: env key holding the scopes string (e.g. ``BOT_SCOPES``).
        @return: list of trimmed scope tokens; empty when the field is unset.
        """
        raw = self._attr(key)
        if not raw:
            return []
        return [scope.strip() for scope in raw.replace(",", " ").split() if scope.strip()]

    def is_complete(self) -> bool:
        """
        @brief Check whether all required bot keys are present.

        @return: ``True`` when :meth:`missing_bot_keys` is empty.
        """
        return not self.missing_bot_keys()

    def as_dict(self) -> dict[str, str]:
        """
        @brief Return a shallow copy of the in-memory env values.

        @return: a new dict mirroring :attr:`_values`.
        """
        return dict(self._values)


def load_twitch_settings(env_path: str | Path | None = None) -> TwitchSettings:
    """
    @brief Module-level shortcut for :meth:`TwitchSettings.load`.

    @param env_path: path to the .env file; defaults to ``.env`` when
        ``None``.
    @return: a fully populated :class:`TwitchSettings` instance.
    """
    return TwitchSettings.load(env_path)


def env_dict_from_environ(environ: dict[str, str] | None = None) -> dict[str, str]:
    """
    @brief Filter an environment mapping down to Twitch-related keys.

    Keeps only keys starting with ``BOT_``, ``TWITCH_``, or ``CHANNEL_``,
    letting callers build a settings dict from :data:`os.environ` or a
    custom environment snapshot.

    @param environ: source mapping; defaults to :data:`os.environ` when
        ``None``.
    @return: dict of Twitch-prefixed keys and their string values.
    """
    env = environ if environ is not None else os.environ
    return {key: value for key, value in env.items() if key.startswith(("BOT_", "TWITCH_", "CHANNEL_"))}


__all__ = [
    "BOT_REQUIRED_KEYS",
    "BOT_SCOPES",
    "CHANNEL_SCOPES",
    "TwitchSettings",
    "load_twitch_settings",
    "parse_env_text",
    "serialize_env",
    "env_dict_from_environ",
]
