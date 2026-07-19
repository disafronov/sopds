from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.signals import connection_created
from django.dispatch import receiver

loglevels = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "none": logging.NOTSET,
}
NOZIP_FORMATS = ["epub", "mobi"]

TITLE = getattr(settings, "SOPDS_TITLE", "SimpleOPDS")
ICON = getattr(settings, "SOPDS_ICON", "/static/images/favicon.ico")
THUMB_SIZE = 100

loglevel = getattr(settings, "SOPDS_LOGLEVEL", "info")
if loglevel.lower() in loglevels:
    LOGLEVEL = loglevels[loglevel.lower()]
else:
    LOGLEVEL = logging.NOTSET

# from constance.signals import config_updated
#
# @receiver(config_updated)
# def constance_updated(sender, updated_key, new_value, **kwargs):
#    if updated_key == 'SOPDS_LANGUAGE':
#        translation.activate(new_value)
#        print(new_value)


def constance_update_all() -> None:
    pass


# Переопределяем некоторые функции для SQLite, которые работают неправлено


def sopds_upper(s: str) -> str:
    return s.upper()


def sopds_substring(s: str, i: int, length: int) -> str:
    i = i - 1
    return s[i : i + length]


def sopds_concat(s1: str = "", s2: str = "", s3: str = "") -> str:
    return "%s%s%s" % (s1, s2, s3)


@receiver(connection_created)
def extend_sqlite(connection: BaseDatabaseWrapper | None = None, **kwargs: Any) -> None:
    if connection is not None and connection.vendor == "sqlite":
        connection.connection.create_function("upper", 1, sopds_upper)
        connection.connection.create_function("substring", 3, sopds_substring)
        connection.connection.create_function("concat", 3, sopds_concat)
