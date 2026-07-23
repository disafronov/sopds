from __future__ import annotations

import logging

from django.conf import settings

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
