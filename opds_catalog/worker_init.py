"""Worker process initialization for multiprocessing.

This module has NO Django or constance imports at the top level so it can
be safely unpickled by spawn-based workers before Django is ready.
"""

import os


def init_worker() -> None:
    """Initialize Django in spawned worker processes."""
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sopds.settings")
    django.setup()
