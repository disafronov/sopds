from unittest.mock import MagicMock, Mock, call, patch

from django.db import connections
from django.test import SimpleTestCase, TransactionTestCase

from opds_catalog.scan_lock import (
    LOCK_ID,
    LOCK_NAME,
    _acquire,
    _release,
    scanner_lock,
)


class ScannerLockTestCase(SimpleTestCase):
    def _connection(self, vendor: str, result: object) -> tuple[Mock, Mock]:
        cursor = Mock()
        cursor.fetchone.return_value = (result,)
        connection = MagicMock(vendor=vendor)
        connection.cursor.return_value.__enter__.return_value = cursor
        return connection, cursor

    def test_postgresql_lock_is_acquired_and_released(self) -> None:
        connection, cursor = self._connection("postgresql", True)

        with patch("opds_catalog.scan_lock.connections") as registry:
            registry.__getitem__.return_value = connection
            with scanner_lock() as acquired:
                self.assertTrue(acquired)

        self.assertEqual(
            cursor.execute.call_args_list,
            [
                call("SELECT pg_try_advisory_lock(%s)", [LOCK_ID]),
                call("SELECT pg_advisory_unlock(%s)", [LOCK_ID]),
            ],
        )
        connection.close.assert_called_once_with()

    def test_mysql_busy_lock_is_not_released(self) -> None:
        connection, cursor = self._connection("mysql", 0)

        with patch("opds_catalog.scan_lock.connections") as registry:
            registry.__getitem__.return_value = connection
            with scanner_lock() as acquired:
                self.assertFalse(acquired)

        cursor.execute.assert_called_once_with("SELECT GET_LOCK(%s, 0)", [LOCK_NAME])
        connection.close.assert_called_once_with()


class ScannerLockDatabaseTestCase(TransactionTestCase):
    databases = {"default", "scanner_lock"}

    def test_lock_excludes_a_second_database_connection(self) -> None:
        second_connection = connections["default"]

        with scanner_lock() as acquired:
            self.assertTrue(acquired)
            self.assertFalse(_acquire(second_connection))

        self.assertTrue(_acquire(second_connection))
        _release(second_connection)
