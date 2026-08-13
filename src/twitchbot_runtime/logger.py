"""Pluggable logger wrapper with severity filtering and swappable sinks.

The runtime talks to :class:`Logger` exclusively instead of the stdlib
``logging`` module directly. A :class:`LogSink` decides where records go
(stdlib logging by default), so the destination can be swapped later
(JSON file, syslog, websocket UI, ...) without touching call sites.

Usage::

    from twitchbot_runtime.logger import get_logger

    logger = get_logger(__name__)
    logger.info("Tunnel public URL: %s", url)
    logger.exception("Subscription registration failed")
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from enum import IntEnum
from types import TracebackType
from typing import Any, Protocol, runtime_checkable


class Severity(IntEnum):
    """Ordered log severity levels (mirrors stdlib logging levels)."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


@runtime_checkable
class LogSink(Protocol):
    """Destination interface for formatted log records.

    Implementations receive the already-resolved severity and message
    template args; ``exc_info`` is forwarded for ``exception`` calls.
    """

    def emit(
        self,
        name: str,
        severity: Severity,
        message: str,
        *args: Any,
        exc_info: BaseException | tuple[type[BaseException], BaseException, TracebackType] | None = None,
    ) -> None:
        ...


class StdlibLogSink:
    """Default sink delegating to the standard library logging tree.

    Keeps the existing per-module loggers (``logging.getLogger(name)``)
    so handlers/formatters configured elsewhere keep working unchanged.
    """

    def emit(
        self,
        name: str,
        severity: Severity,
        message: str,
        *args: Any,
        exc_info: BaseException | tuple[type[BaseException], BaseException, TracebackType] | None = None,
    ) -> None:
        stdlib_logger = logging.getLogger(name)
        stdlib_logger.log(int(severity), message, *args, exc_info=exc_info)


class Logger:
    """Severity-filtered logger forwarding records to a :class:`LogSink`.

    A logger is cheap to create and safe to keep as a module-level
    constant. The active severity threshold is read live from the
    global config so callers can raise/lower it at runtime.
    """

    __slots__ = ("_name", "_sink_override")

    def __init__(self, name: str, sink: LogSink | None = None) -> None:
        self._name = name
        self._sink_override = sink

    @property
    def name(self) -> str:
        return self._name

    @property
    def sink(self) -> LogSink:
        return self._sink_override if self._sink_override is not None else _config.sink

    def is_enabled(self, severity: Severity) -> bool:
        return int(severity) >= int(_config.min_severity)

    def _log(
        self,
        severity: Severity,
        message: str,
        *args: Any,
        exc_info: BaseException | tuple[type[BaseException], BaseException, TracebackType] | None = None,
    ) -> None:
        if not self.is_enabled(severity):
            return
        self.sink.emit(self._name, severity, message, *args, exc_info=exc_info)

    def debug(self, message: str, *args: Any) -> None:
        self._log(Severity.DEBUG, message, *args)

    def info(self, message: str, *args: Any) -> None:
        self._log(Severity.INFO, message, *args)

    def warning(self, message: str, *args: Any) -> None:
        self._log(Severity.WARNING, message, *args)

    def warn(self, message: str, *args: Any) -> None:
        self._log(Severity.WARNING, message, *args)

    def error(self, message: str, *args: Any) -> None:
        self._log(Severity.ERROR, message, *args)

    def critical(self, message: str, *args: Any) -> None:
        self._log(Severity.CRITICAL, message, *args)

    def exception(self, message: str, *args: Any, exc_info: BaseException | bool | None = True) -> None:
        """Log an ERROR with exception info. Defaults to the active exception."""
        resolved: BaseException | tuple[type[BaseException], BaseException, TracebackType] | None
        if exc_info is True:
            resolved = _active_exception()
        elif exc_info is False or exc_info is None:
            resolved = None
        else:
            resolved = exc_info
        self._log(Severity.ERROR, message, *args, exc_info=resolved)


def _active_exception() -> tuple[type[BaseException], BaseException, TracebackType] | None:
    import sys

    info = sys.exc_info()
    if info[0] is None:
        return None
    return info


class _LogConfig:
    """Process-wide logger configuration (sink + min severity)."""

    __slots__ = ("min_severity", "sink")

    def __init__(self) -> None:
        self.min_severity: Severity = Severity.INFO
        self.sink: LogSink = StdlibLogSink()


_config = _LogConfig()


def configure(
    *,
    min_severity: Severity | None = None,
    sink: LogSink | None = None,
) -> None:
    """Update global logger configuration.

    Passing ``min_severity`` raises/lowers the threshold for every
    :class:`Logger` created from :func:`get_logger` (existing loggers
    pick up the change live because they read the config on each call).
    Passing ``sink`` swaps the destination (e.g. a JSON sink or a test
    capture). Either keyword may be omitted to keep the prior value.
    """
    if min_severity is not None:
        _config.min_severity = min_severity
    if sink is not None:
        _config.sink = sink


def get_logger(name: str, sink: LogSink | None = None) -> Logger:
    """Return a :class:`Logger` for ``name`` (typically ``__name__``)."""
    return Logger(name, sink)


# Alias kept for symmetry with the stdlib factory name; lets call sites
# do ``from twitchbot_runtime.logger import getLogger`` if preferred.
getLogger: Callable[[str], Logger] = get_logger
