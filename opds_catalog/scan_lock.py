"""Cross-process scanner lock backed by the configured database."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper

LOCK_ALIAS = "scanner_lock"
LOCK_NAME = "sopds.scanner"
LOCK_ID = int.from_bytes(LOCK_NAME.encode(), byteorder="big") % (2**63)


def _acquire(connection: BaseDatabaseWrapper) -> bool:
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_ID])
        elif connection.vendor == "mysql":
            cursor.execute("SELECT GET_LOCK(%s, 0)", [LOCK_NAME])
        else:  # pragma: no cover - settings reject unsupported backends
            raise RuntimeError(f"Unsupported scanner lock backend: {connection.vendor}")
        row = cursor.fetchone()
    return bool(row and row[0])


def _release(connection: BaseDatabaseWrapper) -> None:
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])
        elif connection.vendor == "mysql":
            cursor.execute("SELECT RELEASE_LOCK(%s)", [LOCK_NAME])
        else:  # pragma: no cover - acquisition rejects unsupported backends
            raise RuntimeError(f"Unsupported scanner lock backend: {connection.vendor}")


@contextmanager
def scanner_lock() -> Iterator[bool]:
    """Yield whether the process acquired the global scanner lock."""
    connection = connections[LOCK_ALIAS]
    acquired = False
    try:
        acquired = _acquire(connection)
        yield acquired
    finally:
        if acquired:
            _release(connection)
        connection.close()
