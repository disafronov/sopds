"""Management command: supervised launcher for runserver + scanner (dev only)."""

import sys

from django.core.management.base import BaseCommand

from ..supervisor import _spawn, _supervise


class Command(BaseCommand):
    """Spawn runserver and the scanner as supervised children (development only)."""

    help = "Start runserver and the scanner together for local development"

    def handle(self, *args: object, **_options: object) -> None:
        """Launch child processes and hand off to the supervisor loop."""
        _supervise(
            [
                _spawn(sys.executable, "manage.py", "sopds_scanner", "start"),
                _spawn(sys.executable, "manage.py", "runserver", "0.0.0.0:8000"),
            ]
        )
