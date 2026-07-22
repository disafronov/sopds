from __future__ import annotations

import logging
import sys
from argparse import ArgumentParser
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from constance import config
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connections

from opds_catalog.models import Counter
from opds_catalog.scan_lock import scanner_lock
from opds_catalog.sopdscan import opdsScanner


class Command(BaseCommand):
    help = "Scan Books Collection."
    scan_is_active: bool = False
    logger: logging.Logger = logging.getLogger("opds_catalog.scanner")
    sched: BlockingScheduler | None = None  # Initialized in start(); annotations only.
    SCAN_SHED_DAY: str = ""
    SCAN_SHED_DOW: str = ""
    SCAN_SHED_HOUR: str = ""
    SCAN_SHED_MIN: str = ""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("command", choices=("scan", "start"))

    def handle(self, *args: Any, **options: Any) -> None:
        action = options["command"]
        self.logger = logging.getLogger("opds_catalog.scanner")

        if action == "scan":
            self.stdout.write("Startup once book-scan.")
            self.scan(suppress_errors=False)
            self.stdout.write("Complete book-scan.")
        elif action == "start":
            self.start()

    def scan(self, *, suppress_errors: bool = True) -> None:
        if self.scan_is_active:
            self.stdout.write("Scan process already active. Skip currend job.")
            return

        self.scan_is_active = True
        try:
            close_old_connections()

            with scanner_lock() as acquired:
                if not acquired:
                    self.stdout.write("Scan process already active in another process.")
                    return

                scanner = opdsScanner(self.logger)
                scanner.scan_all()
                Counter.objects.update_known_counters()
        except Exception:
            self.logger.exception("Scan failed with an unhandled exception")
            if not suppress_errors:
                raise
        finally:
            self.scan_is_active = False
            connections.close_all()

    def update_shedule(self) -> None:
        self.SCAN_SHED_DAY = config.SOPDS_SCAN_SHED_DAY
        self.SCAN_SHED_DOW = config.SOPDS_SCAN_SHED_DOW
        self.SCAN_SHED_HOUR = config.SOPDS_SCAN_SHED_HOUR
        self.SCAN_SHED_MIN = config.SOPDS_SCAN_SHED_MIN
        self.stdout.write(
            "Reconfigure scheduled book-scan (min=%s, hour=%s, day_of_week=%s, day=%s)."
            % (
                self.SCAN_SHED_MIN,
                self.SCAN_SHED_HOUR,
                self.SCAN_SHED_DOW,
                self.SCAN_SHED_DAY,
            )
        )
        # self.sched is always assigned in start() before any scheduled job runs.
        assert self.sched is not None
        self.sched.reschedule_job(
            "scan",
            trigger="cron",
            day=self.SCAN_SHED_DAY,
            day_of_week=self.SCAN_SHED_DOW,
            hour=self.SCAN_SHED_HOUR,
            minute=self.SCAN_SHED_MIN,
        )

    def check_settings(self) -> None:
        close_old_connections()
        if not (
            self.SCAN_SHED_MIN == config.SOPDS_SCAN_SHED_MIN
            and self.SCAN_SHED_HOUR == config.SOPDS_SCAN_SHED_HOUR
            and self.SCAN_SHED_DOW == config.SOPDS_SCAN_SHED_DOW
            and self.SCAN_SHED_DAY == config.SOPDS_SCAN_SHED_DAY
        ):
            self.update_shedule()
        if config.SOPDS_SCAN_START_DIRECTLY:
            config.SOPDS_SCAN_START_DIRECTLY = False
            self.stdout.write(
                "Startup scannyng directly by SOPDS_SCAN_START_DIRECTLY flag."
            )
            # self.sched is always assigned in start() before any scheduled job runs.
            assert self.sched is not None
            self.sched.add_job(self.scan, id="scan_directly")
        connections.close_all()

    def start(self) -> None:
        self.SCAN_SHED_DAY = config.SOPDS_SCAN_SHED_DAY
        self.SCAN_SHED_DOW = config.SOPDS_SCAN_SHED_DOW
        self.SCAN_SHED_HOUR = config.SOPDS_SCAN_SHED_HOUR
        self.SCAN_SHED_MIN = config.SOPDS_SCAN_SHED_MIN
        self.stdout.write(
            "Startup scheduled book-scan (min=%s, hour=%s, day_of_week=%s, day=%s)."
            % (
                self.SCAN_SHED_MIN,
                self.SCAN_SHED_HOUR,
                self.SCAN_SHED_DOW,
                self.SCAN_SHED_DAY,
            )
        )
        self.sched = BlockingScheduler()
        self.sched.add_job(
            self.scan,
            "cron",
            day=self.SCAN_SHED_DAY,
            day_of_week=self.SCAN_SHED_DOW,
            hour=self.SCAN_SHED_HOUR,
            minute=self.SCAN_SHED_MIN,
            id="scan",
        )
        self.sched.add_job(self.check_settings, "cron", minute="*/5", id="check")
        quit_command = "CTRL-BREAK" if sys.platform == "win32" else "CONTROL-C"
        self.stdout.write("Quit the server with %s.\n" % quit_command)
        try:
            self.sched.start()
        except (KeyboardInterrupt, SystemExit):
            pass
