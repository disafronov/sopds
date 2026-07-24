import os
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZIP_STORED
from zipfile import ZipFile as StandardZipFile
from zipfile import ZipInfo

from django.test import SimpleTestCase

from opds_catalog import zipf as zipfile


class LegacyZipInfo(ZipInfo):
    def _encodeFilenameFlags(self) -> tuple[bytes, int]:
        return self.filename.encode("cp866"), self.flag_bits & ~0x800


class ZipTestCase(SimpleTestCase):
    test_module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_ROOTLIB = os.path.join(test_module_path, "tests/data")
    test_zip = "books.zip"
    test_bad_zip = "badfile.zip"

    def setUp(self) -> None:
        self.config_patch = patch.object(
            zipfile, "config", SimpleNamespace(SOPDS_ZIP_CODEPAGE="cp866")
        )
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def test_zip_valid(self) -> None:
        z = zipfile.ZipFile(
            os.path.join(self.test_ROOTLIB, self.test_zip), "r", allowZip64=True
        )
        filelist = z.namelist()
        file_size = z.getinfo("539485.fb2").file_size
        file = z.open("539485.fb2")
        self.assertListEqual(filelist, ["539603.fb2", "539485.fb2", "539273.fb2"])
        self.assertEqual(file_size, 12293)
        self.assertEqual(file.read(38), b'<?xml version="1.0" encoding="utf-8"?>')
        file.close()

    def test_zip_novalid(self) -> None:
        bad_file_count = 0
        try:
            zipfile.ZipFile(
                os.path.join(self.test_ROOTLIB, self.test_bad_zip), "r", allowZip64=True
            )
        except zipfile.BadZipFile:
            bad_file_count = 1

        self.assertEqual(bad_file_count, 1)

    def test_configured_metadata_encoding(self) -> None:
        archive = BytesIO()
        with StandardZipFile(archive, "w") as zf:
            info = LegacyZipInfo("книга.fb2")
            info.compress_type = ZIP_STORED
            zf.writestr(info, b"book")
        archive.seek(0)

        with patch.object(
            zipfile, "config", SimpleNamespace(SOPDS_ZIP_CODEPAGE="cp866")
        ):
            with zipfile.ZipFile(archive) as zf:
                self.assertEqual(zf.namelist(), ["книга.fb2"])
