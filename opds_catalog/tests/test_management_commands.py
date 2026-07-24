from __future__ import annotations

from contextlib import nullcontext
from io import StringIO
from typing import Any
from unittest.mock import Mock, call, patch

from django.test import SimpleTestCase

from opds_catalog.management.commands.sopds_scanner import Command as ScanCommand
from opds_catalog.management.commands.sopds_util import Command as UtilCommand


class ScannerCommandTestCase(SimpleTestCase):
    def setUp(self) -> None:
        self.command = ScanCommand(stdout=StringIO())

    @patch.object(ScanCommand, "start")
    @patch.object(ScanCommand, "scan")
    def test_handle_dispatches_foreground_actions(
        self, scan: Mock, start: Mock
    ) -> None:
        self.command.handle(command="scan")
        scan.assert_called_once_with(suppress_errors=False)
        self.assertIn("Complete book-scan", self.command.stdout.getvalue())

        self.command.handle(command="start")
        start.assert_called_once_with()

    @patch("opds_catalog.management.commands.sopds_scanner.connections")
    def test_scan_skips_overlapping_run(self, connections: Mock) -> None:
        self.command.scan_is_active = True

        self.command.scan()

        self.assertIn("already active", self.command.stdout.getvalue())
        connections.close_all.assert_not_called()

    @patch("opds_catalog.management.commands.sopds_scanner.Counter")
    @patch("opds_catalog.management.commands.sopds_scanner.opdsScanner")
    @patch("opds_catalog.management.commands.sopds_scanner.scanner_lock")
    @patch("opds_catalog.management.commands.sopds_scanner.connections")
    @patch("opds_catalog.management.commands.sopds_scanner.close_old_connections")
    def test_scan_closes_connections_and_updates_counters(
        self,
        close_old_connections: Mock,
        connections: Mock,
        lock: Mock,
        scanner_class: Mock,
        counter: Mock,
    ) -> None:
        lock.return_value = nullcontext(True)

        self.command.scan()

        close_old_connections.assert_called_once_with()
        scanner_class.return_value.scan_all.assert_called_once_with()
        counter.objects.update_known_counters.assert_called_once_with()
        connections.close_all.assert_called_once_with()
        self.assertFalse(self.command.scan_is_active)

    @patch("opds_catalog.management.commands.sopds_scanner.opdsScanner")
    @patch("opds_catalog.management.commands.sopds_scanner.scanner_lock")
    @patch("opds_catalog.management.commands.sopds_scanner.connections")
    @patch("opds_catalog.management.commands.sopds_scanner.close_old_connections")
    def test_scan_skips_lock_held_by_another_process(
        self,
        close_old_connections: Mock,
        connections: Mock,
        lock: Mock,
        scanner_class: Mock,
    ) -> None:
        lock.return_value = nullcontext(False)

        self.command.scan()

        close_old_connections.assert_called_once_with()
        scanner_class.assert_not_called()
        self.assertIn("another process", self.command.stdout.getvalue())
        self.assertFalse(self.command.scan_is_active)
        connections.close_all.assert_called_once_with()

    @patch("opds_catalog.management.commands.sopds_scanner.connections")
    @patch("opds_catalog.management.commands.sopds_scanner.close_old_connections")
    @patch("opds_catalog.management.commands.sopds_scanner.config")
    def test_check_settings_reloads_changed_database_schedule(
        self, config: Mock, close_old_connections: Mock, connections: Mock
    ) -> None:
        config.SOPDS_SCAN_SHED_DAY = "2"
        config.SOPDS_SCAN_SHED_DOW = "mon"
        config.SOPDS_SCAN_SHED_HOUR = "3"
        config.SOPDS_SCAN_SHED_MIN = "4"
        config.SOPDS_SCAN_START_DIRECTLY = False
        self.command.sched = Mock()

        self.command.check_settings()

        self.command.sched.reschedule_job.assert_called_once_with(
            "scan",
            trigger="cron",
            day="2",
            day_of_week="mon",
            hour="3",
            minute="4",
        )
        close_old_connections.assert_called_once_with()
        connections.close_all.assert_called_once_with()

    @patch("opds_catalog.management.commands.sopds_scanner.connections")
    @patch("opds_catalog.management.commands.sopds_scanner.close_old_connections")
    @patch("opds_catalog.management.commands.sopds_scanner.config")
    def test_check_settings_consumes_direct_scan_flag(
        self, config: Mock, close_old_connections: Mock, connections: Mock
    ) -> None:
        config.SOPDS_SCAN_SHED_DAY = "*"
        config.SOPDS_SCAN_SHED_DOW = "*"
        config.SOPDS_SCAN_SHED_HOUR = "*"
        config.SOPDS_SCAN_SHED_MIN = "0"
        config.SOPDS_SCAN_START_DIRECTLY = True
        self.command.SCAN_SHED_DAY = "*"
        self.command.SCAN_SHED_DOW = "*"
        self.command.SCAN_SHED_HOUR = "*"
        self.command.SCAN_SHED_MIN = "0"
        self.command.sched = Mock()

        self.command.check_settings()

        self.assertFalse(config.SOPDS_SCAN_START_DIRECTLY)
        self.command.sched.add_job.assert_called_once_with(
            self.command.scan, id="scan_directly"
        )

    @patch("opds_catalog.management.commands.sopds_scanner.BlockingScheduler")
    @patch("opds_catalog.management.commands.sopds_scanner.config")
    def test_start_configures_scheduler_from_database(
        self, config: Mock, scheduler_class: Mock
    ) -> None:
        config.SOPDS_SCAN_SHED_DAY = "1"
        config.SOPDS_SCAN_SHED_DOW = "tue"
        config.SOPDS_SCAN_SHED_HOUR = "5"
        config.SOPDS_SCAN_SHED_MIN = "15"
        scheduler = scheduler_class.return_value

        self.command.start()

        self.assertEqual(
            scheduler.add_job.call_args_list,
            [
                call(
                    self.command.scan,
                    "cron",
                    day="1",
                    day_of_week="tue",
                    hour="5",
                    minute="15",
                    id="scan",
                ),
                call(self.command.check_settings, "cron", minute="*/5", id="check"),
            ],
        )
        scheduler.start.assert_called_once_with()

    @patch("opds_catalog.management.commands.sopds_scanner.BlockingScheduler")
    @patch("opds_catalog.management.commands.sopds_scanner.config")
    def test_start_treats_interrupt_as_clean_shutdown(
        self, config: Mock, scheduler_class: Mock
    ) -> None:
        config.SOPDS_SCAN_SHED_DAY = "*"
        config.SOPDS_SCAN_SHED_DOW = "*"
        config.SOPDS_SCAN_SHED_HOUR = "*"
        config.SOPDS_SCAN_SHED_MIN = "0"
        scheduler_class.return_value.start.side_effect = KeyboardInterrupt

        self.command.start()


class UtilCommandTestCase(SimpleTestCase):
    def setUp(self) -> None:
        self.command = UtilCommand(stdout=StringIO())

    @patch("opds_catalog.management.commands.sopds_util.call_command")
    def test_configuration_commands(self, call_command: Mock) -> None:
        self.command.handle(
            command=["setconf", "SOPDS_ZIP_ENABLE", "True"],
            verbose=False,
            nogenres=False,
        )
        call_command.assert_called_once_with(
            "constance", "set", "SOPDS_ZIP_ENABLE", "True"
        )

        call_command.reset_mock()
        self.command.handle(command=["getconf"], verbose=False, nogenres=False)
        call_command.assert_called_once_with("constance", "list")

        call_command.reset_mock()
        self.command.handle(
            command=["getconf", "SOPDS_ZIP_ENABLE"], verbose=False, nogenres=False
        )
        call_command.assert_called_once_with("constance", "get", "SOPDS_ZIP_ENABLE")

    @patch("opds_catalog.management.commands.sopds_util.opdsdb")
    def test_pg_optimize_dispatch(self, opdsdb: Any) -> None:
        self.command.handle(command=["pg_optimize"], verbose=False, nogenres=False)
        opdsdb.pg_optimize.assert_called_once_with(True)

    @patch("opds_catalog.management.commands.sopds_util.Counter")
    @patch("opds_catalog.management.commands.sopds_util.call_command")
    @patch("opds_catalog.management.commands.sopds_util.opdsdb")
    @patch("opds_catalog.management.commands.sopds_util.transaction.atomic")
    def test_clear_rebuilds_default_genres_and_counters(
        self, atomic: Mock, opdsdb: Mock, call_command: Mock, counter: Mock
    ) -> None:
        self.command.verbose = True

        self.command.clear()

        atomic.return_value.__enter__.assert_called_once_with()
        opdsdb.clear_all.assert_called_once_with(True)
        call_command.assert_called_once_with("loaddata", "genre.json")
        counter.objects.update_known_counters.assert_called_once_with()
        opdsdb.pg_optimize.assert_called_once_with(False)

    @patch("opds_catalog.management.commands.sopds_util.Counter")
    @patch("opds_catalog.management.commands.sopds_util.call_command")
    @patch("opds_catalog.management.commands.sopds_util.opdsdb")
    @patch("opds_catalog.management.commands.sopds_util.transaction.atomic")
    def test_clear_can_preserve_custom_genres(
        self, atomic: Mock, opdsdb: Mock, call_command: Mock, counter: Mock
    ) -> None:
        self.command.nogenres = True

        self.command.clear()

        call_command.assert_not_called()

    @patch("opds_catalog.management.commands.sopds_util.Counter")
    def test_info_prints_all_known_counters(self, counter: Mock) -> None:
        counter.objects.get_counter.side_effect = [1, 2, 3, 4, 5]

        self.command.info()

        self.assertIn("Books count    = 1", self.command.stdout.getvalue())
        self.assertIn("Series count   = 5", self.command.stdout.getvalue())
        self.assertEqual(counter.objects.get_counter.call_count, 5)

    @patch("opds_catalog.management.commands.sopds_util.call_command")
    def test_save_mygenres_uses_project_fixture(self, call_command: Mock) -> None:
        self.command.save_mygenres()

        call_command.assert_called_once_with(
            "dumpdata",
            "opds_catalog.genre",
            "--output",
            "opds_catalog/fixtures/mygenres.json",
        )

    @patch("opds_catalog.management.commands.sopds_util.Counter")
    @patch("opds_catalog.management.commands.sopds_util.call_command")
    @patch("opds_catalog.management.commands.sopds_util.opdsdb")
    def test_load_mygenres_replaces_genres(
        self, opdsdb: Mock, call_command: Mock, counter: Mock
    ) -> None:
        self.command.verbose = True

        self.command.load_mygenres()

        opdsdb.clear_genres.assert_called_once_with(True)
        call_command.assert_called_once_with("loaddata", "mygenres.json")
        counter.objects.update_known_counters.assert_called_once_with()
