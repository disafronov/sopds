from __future__ import annotations

import logging
import os
import signal
import sys
from argparse import ArgumentParser
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from constance import config
from django.conf import settings as main_settings
from django.core.management.base import BaseCommand
from django.db import connection, connections

from opds_catalog import settings
from opds_catalog.models import Counter
from opds_catalog.sopdscan import opdsScanner


class Command(BaseCommand):
    help = "Scan Books Collection."
    scan_is_active: bool = False
    pidfile: str = ""
    logger: logging.Logger = logging.getLogger("")
    sched: BlockingScheduler | None = None  # Initialized in start(); annotations only.
    SCAN_SHED_DAY: str = ""
    SCAN_SHED_DOW: str = ""
    SCAN_SHED_HOUR: str = ""
    SCAN_SHED_MIN: str = ""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("command", help="Use [ scan | start | stop | restart ]")
        parser.add_argument(
            "--verbose",
            action="store_true",
            dest="verbose",
            default=False,
            help="Set verbosity level for books collection scan.",
        )
        parser.add_argument(
            "--daemon",
            action="store_true",
            dest="daemonize",
            default=False,
            help="Daemonize server",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        self.pidfile = os.path.join(
            main_settings.BASE_DIR, main_settings.SOPDS_SCANNER_PID
        )
        action = options["command"]
        self.logger = logging.getLogger("")
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")

        if settings.LOGLEVEL != logging.NOTSET:
            # Создаем обработчик для записи логов в файл
            fh = logging.FileHandler(main_settings.SOPDS_SCANNER_LOG)
            fh.setLevel(settings.LOGLEVEL)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

        if options["verbose"]:
            # Создадим обработчик для вывода логов на экран
            # с максимальным уровнем вывода
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

        if options["daemonize"] and (action in ["start", "scan"]):
            if sys.platform == "win32":
                self.stdout.write("On Windows platform Daemonize not working.")
            else:
                daemonize()

        if action == "scan":
            self.stdout.write("Startup once book-scan.")
            self.scan()
            self.stdout.write("Complete book-scan.")
        elif action == "start":
            self.start()
        elif action == "stop":
            pid = open(self.pidfile, "r").read()
            self.stop(pid)
        elif action == "restart":
            pid = open(self.pidfile, "r").read()
            self.restart(pid)

    def scan(self) -> None:
        if self.scan_is_active:
            self.stdout.write("Scan process already active. Skip currend job.")
            return

        self.scan_is_active = True

        if connection.connection and not connection.is_usable():
            # Access the private per-connection cache to drop a dead connection.
            del connections._connections.default  # type: ignore[attr-defined]

        scanner = opdsScanner(self.logger)
        scanner.scan_all()
        Counter.objects.update_known_counters()
        self.scan_is_active = False

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
        if connection.connection and not connection.is_usable():
            # Access the private per-connection cache to drop a dead connection.
            del connections._connections.default  # type: ignore[attr-defined]
        settings.constance_update_all()
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

    def start(self) -> None:
        writepid(self.pidfile)
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

    def stop(self, pid: str) -> None:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError as e:
            self.stdout.write("Error stopping sopds_scanner: %s" % str(e))

    def restart(self, pid: str) -> None:
        self.stop(pid)
        self.start()


def writepid(pid_file: str) -> None:
    """
    Write the process ID to disk.
    """
    fp = open(pid_file, "w")
    fp.write(str(os.getpid()))
    fp.close()
    return None


def daemonize() -> None:
    """
    Detach from the terminal and continue as a daemon.
    """
    # swiped from twisted/scripts/twistd.py
    # See http://www.erlenstar.demon.co.uk/unix/faq_toc.html#TOC16
    if os.fork():  # launch child and...
        os._exit(0)  # kill off parent
    os.setsid()
    if os.fork():  # launch child and...
        os._exit(0)  # kill off parent again.
    os.umask(0)

    std_in = open("/dev/null", "r")
    std_out = open(main_settings.SOPDS_SCANNER_LOG, "a+")
    os.dup2(std_in.fileno(), sys.stdin.fileno())
    os.dup2(std_out.fileno(), sys.stdout.fileno())
    os.dup2(std_out.fileno(), sys.stderr.fileno())

    #    null = os.open("/dev/null", os.O_RDWR)
    #    for i in range(3):
    #        try:
    #            os.dup2(null, i)
    #        except OSError as e:
    #            if e.errno != errno.EBADF:
    #                raise
    os.close(std_in.fileno())
    os.close(std_out.fileno())
    return None
