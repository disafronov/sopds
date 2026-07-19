from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from opds_catalog.worker_init import init_worker


class WorkerInitializationTestCase(SimpleTestCase):
    @patch("django.setup")
    def test_initializes_django_for_spawned_process(self, setup: object) -> None:
        with patch.dict(os.environ, {}, clear=True):
            init_worker()
            self.assertEqual(os.environ["DJANGO_SETTINGS_MODULE"], "config.settings")

        setup.assert_called_once_with()  # type: ignore[attr-defined]

    @patch("django.setup")
    def test_preserves_explicit_settings_module(self, setup: object) -> None:
        with patch.dict(
            os.environ, {"DJANGO_SETTINGS_MODULE": "custom.settings"}, clear=True
        ):
            init_worker()
            self.assertEqual(os.environ["DJANGO_SETTINGS_MODULE"], "custom.settings")
