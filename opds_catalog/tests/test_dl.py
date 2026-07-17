# -*- coding: utf-8 -*-

from django.test import TestCase


class DownloadsTestCase(TestCase):
    fixtures = ["testdb.json"]

    def setUp(self) -> None:
        pass

    def test_download_book(self) -> None:
        pass

    def test_download_zip(self) -> None:
        pass

    def test_download_cover(self) -> None:
        pass
