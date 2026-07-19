"""Logging filters used by the project-wide Django configuration."""

import logging


class BelowErrorFilter(logging.Filter):
    """Allow records below ERROR so stdout and stderr never duplicate output."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.ERROR
