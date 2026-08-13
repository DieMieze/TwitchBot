import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.logger import (
    Logger,
    Severity,
    StdlibLogSink,
    _config,
    configure,
    get_logger,
)


@pytest.fixture(autouse=True)
def _reset_logger_config():
    original_min = _config.min_severity
    original_sink = _config.sink
    yield
    _config.min_severity = original_min
    _config.sink = original_sink


class RecordingSink:
    def __init__(self):
        self.records = []

    def emit(self, name, severity, message, *args, exc_info=None):
        self.records.append({
            "name": name,
            "severity": severity,
            "message": message,
            "args": args,
            "exc_info": exc_info,
        })


def test_severity_ordering_matches_stdlib():
    assert Severity.DEBUG < Severity.INFO < Severity.WARNING < Severity.ERROR < Severity.CRITICAL
    assert int(Severity.INFO) == logging.INFO
    assert int(Severity.ERROR) == logging.ERROR


def test_get_logger_returns_logger_named_after_module():
    logger = get_logger("twitchbot_runtime.bot")

    assert isinstance(logger, Logger)
    assert logger.name == "twitchbot_runtime.bot"


def test_logger_emits_above_min_severity():
    sink = RecordingSink()
    configure(min_severity=Severity.INFO, sink=sink)
    logger = get_logger("m", sink=sink)

    logger.debug("skipped")
    logger.info("kept: %s", "x")
    logger.warning("warn")

    assert [r["message"] for r in sink.records] == ["kept: %s", "warn"]
    assert sink.records[0]["args"] == ("x",)
    assert sink.records[0]["severity"] == Severity.INFO


def test_logger_filters_below_min_severity():
    sink = RecordingSink()
    configure(min_severity=Severity.WARNING, sink=sink)
    logger = get_logger("m", sink=sink)

    logger.info("nope")
    logger.warning("yes")

    assert [r["message"] for r in sink.records] == ["yes"]


def test_configure_threshold_changes_live_for_existing_loggers():
    sink = RecordingSink()
    configure(min_severity=Severity.WARNING, sink=sink)
    logger = get_logger("m", sink=sink)

    logger.info("ignored")
    configure(min_severity=Severity.DEBUG)
    logger.info("now visible")

    assert [r["message"] for r in sink.records] == ["now visible"]


def test_exception_attaches_active_exc_info():
    sink = RecordingSink()
    configure(min_severity=Severity.DEBUG, sink=sink)
    logger = get_logger("m", sink=sink)

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failure: %s", "ctx")

    assert len(sink.records) == 1
    record = sink.records[0]
    assert record["severity"] == Severity.ERROR
    assert record["message"] == "failure: %s"
    assert record["args"] == ("ctx",)
    assert isinstance(record["exc_info"], tuple)
    assert record["exc_info"][0] is ValueError


def test_exception_without_active_exception_omits_exc_info():
    sink = RecordingSink()
    configure(min_severity=Severity.DEBUG, sink=sink)
    logger = get_logger("m", sink=sink)

    logger.exception("no active exc")

    assert sink.records[0]["exc_info"] is None


def test_exception_with_explicit_exc_info_false():
    sink = RecordingSink()
    configure(min_severity=Severity.DEBUG, sink=sink)
    logger = get_logger("m", sink=sink)

    try:
        raise RuntimeError("x")
    except RuntimeError:
        logger.exception("msg", exc_info=False)

    assert sink.records[0]["exc_info"] is None


def test_warn_is_alias_for_warning():
    sink = RecordingSink()
    configure(min_severity=Severity.DEBUG, sink=sink)
    logger = get_logger("m", sink=sink)

    logger.warn("deprecated alias")

    assert sink.records[0]["severity"] == Severity.WARNING


def test_configure_sink_swap():
    sink_a = RecordingSink()
    sink_b = RecordingSink()
    configure(min_severity=Severity.DEBUG, sink=sink_a)
    logger = get_logger("m")

    logger.info("first")
    configure(sink=sink_b)
    logger.info("second")

    assert [r["message"] for r in sink_a.records] == ["first"]
    assert [r["message"] for r in sink_b.records] == ["second"]


def test_configure_preserves_value_when_omitted():
    sink = RecordingSink()
    configure(min_severity=Severity.WARNING, sink=sink)
    configure()  # nothing changes

    assert _config_min_severity() == Severity.WARNING
    assert _config_sink() is sink


def _config_min_severity():
    from twitchbot_runtime.logger import _config

    return _config.min_severity


def _config_sink():
    from twitchbot_runtime.logger import _config

    return _config.sink


def test_stdlib_sink_forwards_to_logging():
    sink = StdlibLogSink()
    stdlib_logger = logging.getLogger("twitchbot_runtime.test.stdlib_sink")
    stdlib_logger.setLevel(logging.DEBUG)
    captured = []

    class Handler(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    handler = Handler()
    handler.setLevel(logging.DEBUG)
    stdlib_logger.addHandler(handler)
    try:
        sink.emit("twitchbot_runtime.test.stdlib_sink", Severity.WARNING, "hello %s", "world")
    finally:
        stdlib_logger.removeHandler(handler)

    assert captured == ["hello world"]
