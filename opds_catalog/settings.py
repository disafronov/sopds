from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

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
ICON = getattr(settings, "SOPDS_ICON", staticfiles_storage.url("images/favicon.ico"))
THUMB_SIZE = 100

loglevel = getattr(settings, "SOPDS_LOGLEVEL", "info")
if loglevel.lower() in loglevels:
    LOGLEVEL = loglevels[loglevel.lower()]
else:
    LOGLEVEL = logging.NOTSET
