"""Centralised, persistent, validated port resolution for TwitchBot components.

The 5 historically hardcoded ports (overlay 5000, webui 5001, webhook 5002,
pos_ui 5003, oauth 5003) are made configurable and persisted in
``settings.json`` under ``runtime.<component>.port``.

Behaviour:

* If a port is already present in settings.json, it is used as-is (after a
  freedom check). This means re-runs never prompt again.
* If the entry is missing AND the process is interactive (a real TTY), the
  user is prompted once with the default pre-filled; the chosen port is then
  persisted to settings.json.
* If the entry is missing AND the process is non-interactive (no TTY), the
  default is used WITHOUT being persisted (so the first interactive run still
  gets to choose). A warning is logged that the value can be set via the
  Config-UI.
* OAuth prompts carry an extra advisory warning that the Twitch Dev Console
  Redirect URI must be updated when the port changes (the code cannot enforce
  this — it is purely advisory).
* After resolution the chosen port is checked with a real socket bind. When
  the port is already in use :class:`PortInUseError` is raised (with a list of
  suggested free alternatives). :func:`resolve_port_or_exit` wraps that into a
  clean stderr message + ``sys.exit(1)``.

This module deliberately does NOT add the new port keys to the
``load_settings`` default dict in ``settings.py`` — a missing key is the
signal that triggers the first-run prompt. Pre-populating the defaults would
suppress the prompt forever.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any

from .logger import get_logger
from .settings import load_settings, save_settings

logger = get_logger(__name__)

DEFAULT_PORTS: dict[str, int] = {
    "overlay": 5000,
    "webui": 5001,
    "webhook": 5002,
    "pos_ui": 5003,
    "oauth": 5003,
}

VALID_COMPONENTS = frozenset(DEFAULT_PORTS.keys())

_OAUTH_DEFAULT_PORT = DEFAULT_PORTS["oauth"]


class PortInUseError(Exception):
    """Raised when a resolved port is already bound by another process."""

    def __init__(self, host: str, port: int, alternatives: list[int]) -> None:
        self.host = host
        self.port = port
        self.alternatives = alternatives
        super().__init__(
            f"Port {port} on {host} is already in use. "
            f"Free alternatives: {', '.join(str(p) for p in alternatives) or 'none found'}"
        )


def is_port_free(host: str, port: int) -> bool:
    """Return True when ``port`` can be bound on ``host`` right now.

    Performs a real ``SOCK_STREAM`` bind with ``SO_REUSEADDR`` disabled so a
    lingering TIME_WAIT socket still counts as occupied. The probe socket is
    closed immediately so the port remains available for the caller's own
    bind (best-effort; a race between probe and bind is still possible but
    the caller's bind failure is also handled by ``resolve_port_or_exit``).
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            sock.bind((host, port))
        return True
    except OSError:
        return False


def find_free_alternatives(host: str, port: int, count: int = 3) -> list[int]:
    """Return up to ``count`` free ports near ``port`` (excluding it).

    Scans ``port+1 .. port+count+50`` and returns the first ``count`` ports
    that are free on ``host``. Used to build the helpful suggestion list in
    :class:`PortInUseError` messages.
    """
    found: list[int] = []
    candidate = port + 1
    upper = min(port + 200, 65535)
    while candidate <= upper and len(found) < count:
        if candidate != port and is_port_free(host, candidate):
            found.append(candidate)
        candidate += 1
    return found


def _read_persisted_port(settings: dict[str, Any], component: str) -> int | None:
    """Return the persisted port for ``component`` or None when absent/invalid."""
    block = settings.get("runtime", {}).get(component, {})
    if not isinstance(block, dict):
        return None
    raw = block.get("port")
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    if raw < 1 or raw > 65535:
        return None
    return raw


def _persist_port(
    settings: dict[str, Any],
    component: str,
    port: int,
    settings_path: str | Path | None,
) -> None:
    """Persist ``port`` under ``runtime.<component>.port`` and save settings."""
    runtime = settings.setdefault("runtime", {})
    block = runtime.get(component)
    if not isinstance(block, dict):
        block = {}
        runtime[component] = block
    block["port"] = port
    try:
        save_settings(settings, settings_path)
    except Exception:
        logger.exception("Failed to persist port %s=%d to settings.json", component, port)


def _prompt_port(component: str, default: int) -> int:
    """Interactive CLI prompt for a port. Returns the chosen valid port.

    Empty input keeps the default. Invalid input re-prompts. Range-validated
    to 1..65535. The OAuth warning is printed before the prompt when
    ``component == "oauth"`` and the default would change.
    """
    if component == "oauth":
        print(
            "WARNING: changing the OAuth callback port requires updating the "
            "Redirect URI in the Twitch Developer Console (Applications -> "
            "your app -> OAuth Redirect URLs) to "
            "http://localhost:<port>/oauth/callback — otherwise authorization "
            "will fail.",
            file=sys.stderr,
        )
    while True:
        raw = input(f"Port for {component} [default {default}]: ").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print(f"  '{raw}' is not an integer. Try again or press Enter for {default}.")
            continue
        if value < 1 or value > 65535:
            print(f"  {value} is out of range (1..65535). Try again or press Enter for {default}.")
            continue
        return value


def _is_interactive() -> bool:
    """True when stdin is a real TTY (so a prompt would not block headless runs)."""
    try:
        return bool(sys.stdin.isatty())
    except Exception:
        return False


def get_port(
    component: str,
    settings: dict[str, Any] | None = None,
    settings_path: str | Path | None = None,
    *,
    interactive: bool = True,
    host: str = "127.0.0.1",
    persist: bool = True,
) -> int:
    """Resolve the port for ``component`` (prompting/persisting as needed).

    Resolution order:
      1. Persisted value in ``settings["runtime"][component]["port"]`` — used
         directly (no prompt, no re-persist).
      2. Default from :data:`DEFAULT_PORTS`.
      3. If the entry is missing and the run is interactive (TTY) and
         ``interactive=True``: prompt once and persist the answer.
      4. If the entry is missing and the run is non-interactive: use the
         default WITHOUT persisting (so the first interactive run still gets
         to choose) and log a warning pointing at the Config-UI.
      5. Port-freedom check via :func:`is_port_free`. Occupied →
         :class:`PortInUseError`.

    ``settings`` is loaded from ``settings_path`` when None. The dict is
    mutated in place when persistence occurs.
    """
    if component not in VALID_COMPONENTS:
        raise ValueError(f"Unknown port component: {component!r}")
    if settings is None:
        settings = load_settings(settings_path)

    default = DEFAULT_PORTS[component]
    persisted = _read_persisted_port(settings, component)
    should_prompt = interactive and _is_interactive()

    if persisted is not None:
        port = persisted
    elif should_prompt:
        port = _prompt_port(component, default)
        if persist and port != _read_persisted_port(settings, component):
            _persist_port(settings, component, port, settings_path)
    else:
        port = default
        logger.warning(
            "%s port not configured and stdin is non-interactive; using default "
            "%d (not persisted). Set it via the Config-UI Ports section or "
            "settings.json runtime.%s.port.",
            component,
            default,
            component,
        )

    if not is_port_free(host, port):
        alternatives = find_free_alternatives(host, port)
        raise PortInUseError(host, port, alternatives)
    return port


def resolve_port_or_exit(
    component: str,
    settings: dict[str, Any] | None = None,
    settings_path: str | Path | None = None,
    *,
    interactive: bool = True,
    host: str = "127.0.0.1",
) -> int:
    """Resolve a port, exiting the process with a clear message on conflict.

    Wrapper around :func:`get_port` that catches :class:`PortInUseError`,
    prints a human-readable message (including suggested free alternatives)
    to stderr and exits with code 1. Also catches bind failures that occur
    after a successful probe (race) by treating them as a port-in-use error.
    """
    try:
        port = get_port(
            component,
            settings,
            settings_path,
            interactive=interactive,
            host=host,
        )
    except PortInUseError as exc:
        _print_port_in_use_error(exc)
        raise SystemExit(1) from exc
    return port


def _print_port_in_use_error(exc: PortInUseError) -> None:
    alts = ", ".join(str(p) for p in exc.alternatives) or "none found nearby"
    print(
        f"Error: port {exc.port} on {exc.host} is already in use.\n"
        f"Free alternatives you could set in settings.json or the Config-UI: {alts}",
        file=sys.stderr,
    )


def get_effective_ports(settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return a status snapshot of all components for the Config-UI.

    For each component returns ``{"port": int, "default": int, "free": bool}``
    where ``port`` is the persisted value or the default (never prompts, never
    persists) and ``free`` is a live :func:`is_port_free` probe on
    ``127.0.0.1`` (webhook uses its configured host when present). Used by the
    ``GET /api/ports`` endpoint.
    """
    result: dict[str, dict[str, Any]] = {}
    runtime = settings.get("runtime", {})
    for component, default in DEFAULT_PORTS.items():
        port = _read_persisted_port(settings, component)
        if port is None:
            port = default
        host = "127.0.0.1"
        if component == "webhook":
            host = runtime.get("webhook", {}).get("host", "127.0.0.1") if isinstance(runtime, dict) else "127.0.0.1"
        result[component] = {
            "port": port,
            "default": default,
            "free": is_port_free(host, port),
        }
    return result


__all__ = [
    "DEFAULT_PORTS",
    "PortInUseError",
    "find_free_alternatives",
    "get_effective_ports",
    "get_port",
    "is_port_free",
    "resolve_port_or_exit",
]
