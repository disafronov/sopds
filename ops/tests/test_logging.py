"""Tests for project-wide logging stream routing."""

import logging
from typing import Any, cast

from django.conf import settings

from config.logging_filters import BelowErrorFilter


def _record(level: int) -> logging.LogRecord:
    return logging.LogRecord("test", level, __file__, 1, "message", (), None)


def test_below_error_filter_routes_non_errors_to_stdout() -> None:
    log_filter = BelowErrorFilter()

    assert log_filter.filter(_record(logging.DEBUG))
    assert log_filter.filter(_record(logging.INFO))
    assert log_filter.filter(_record(logging.WARNING))
    assert not log_filter.filter(_record(logging.ERROR))
    assert not log_filter.filter(_record(logging.CRITICAL))


def test_django_debug_logging_stays_disabled() -> None:
    logging_config = cast(dict[str, Any], settings.LOGGING)
    assert logging_config["loggers"]["django"]["level"] == "INFO"
