"""Management command: supervised launcher for gunicorn + scanner."""

import sys

from django.core.management.base import BaseCommand

from ..supervisor import _spawn, _supervise


class Command(BaseCommand):
    """Spawn gunicorn and the scanner under a common supervisor."""

    help = "Start gunicorn and the scanner under a common supervisor"

    def handle(self, *args: object, **_options: object) -> None:
        """Launch child processes and hand off to the supervisor loop."""
        _supervise(
            [
                _spawn(sys.executable, "manage.py", "sopds_scanner", "start"),
                _spawn("gunicorn", "sopds.wsgi:application"),
            ]
        )
