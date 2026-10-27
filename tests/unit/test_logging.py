import json
import logging

from tenant_web.infrastructure.logging import JsonFormatter, configure_logging


def _record(**extra):
    record = logging.LogRecord("tenant_web", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.__dict__.update(extra)
    return record


def test_a_record_becomes_one_json_line_with_extra_fields():
    line = JsonFormatter().format(_record(redis_host="redis"))
    entry = json.loads(line)
    assert (entry["level"], entry["logger"], entry["msg"], entry["redis_host"]) == (
        "INFO",
        "tenant_web",
        "hello world",
        "redis",
    )
    assert "\n" not in line


def test_an_exception_is_included_as_text():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    assert "ValueError: boom" in json.loads(JsonFormatter().format(record))["exc"]


def test_configure_logging_installs_one_json_handler_at_the_level():
    configure_logging("WARNING")
    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
