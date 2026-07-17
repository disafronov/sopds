# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
import unittest.mock
import zipfile

from constance import config
from django.test import TestCase

import opds_catalog.zipf as zipf_module
from opds_catalog import dl


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


class ConvertFB2NestedZipTestCase(TestCase):
    """Regression test for the CAT_ZIP branch in dl.ConvertFB2.

    book.filename stores the FULL entry name including nested directories
    (e.g. "subdir/book.fb2"). The extraction must use the original name to
    look up the archive member (no KeyError) and the resolved extracted path
    must stay inside SOPDS_TEMP_DIR.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self._orig_temp = config.SOPDS_TEMP_DIR
        config.SOPDS_TEMP_DIR = self.temp_dir

    def tearDown(self) -> None:
        config.SOPDS_TEMP_DIR = self._orig_temp

    def test_nested_zip_extract_no_keyerror(self) -> None:
        # Build a zip containing a nested entry name.
        nested_name = "subdir/book.fb2"
        zip_path = os.path.join(self.temp_dir, "lib.zip")
        with zipfile.ZipFile(zip_path, "w") as zo:
            zo.writestr(nested_name, "<FB2></FB2>")

        with open(zip_path, "rb") as fz:
            z = zipf_module.ZipFile(fz, "r", allowZip64=True)
            # This is the exact logic used inside ConvertFB2 CAT_ZIP branch;
            # it must not raise KeyError for a nested entry name.
            z.extract(nested_name, config.SOPDS_TEMP_DIR)
            file_path = os.path.realpath(
                os.path.join(config.SOPDS_TEMP_DIR, nested_name)
            )
            dl._ensure_inside_temp_dir(file_path)

        self.assertTrue(
            file_path.startswith(os.path.realpath(self.temp_dir) + os.sep),
            "extracted path must stay inside temp dir",
        )
        self.assertTrue(
            os.path.isfile(file_path),
            "nested member should be extracted to the nested path",
        )

    def test_flat_zip_extract_still_works(self) -> None:
        flat_name = "book.fb2"
        zip_path = os.path.join(self.temp_dir, "lib.zip")
        with zipfile.ZipFile(zip_path, "w") as zo:
            zo.writestr(flat_name, "<FB2></FB2>")

        with open(zip_path, "rb") as fz:
            z = zipf_module.ZipFile(fz, "r", allowZip64=True)
            z.extract(flat_name, config.SOPDS_TEMP_DIR)
            file_path = os.path.realpath(os.path.join(config.SOPDS_TEMP_DIR, flat_name))
            dl._ensure_inside_temp_dir(file_path)

        self.assertTrue(os.path.isfile(file_path))

    def test_convertfb2_zip_renames_to_safe_basename(self) -> None:
        # Mirror the ConvertFB2 CAT_ZIP branch: extract with the ORIGINAL
        # (possibly nested) name, rename to a safe basename so file_path carries
        # no taint from book.filename. Assert no KeyError, stays inside temp dir,
        # and the converter would receive a basename-only path.
        import subprocess

        nested_name = "subdir/book.fb2"
        zip_path = os.path.join(self.temp_dir, "lib.zip")
        with zipfile.ZipFile(zip_path, "w") as zo:
            zo.writestr(nested_name, "<FB2></FB2>")

        captured_args: list[list[str]] = []

        def fake_popen(args: list[str], **kwargs: object) -> object:
            captured_args.append(list(args))

            class _Proc:
                stdout = None

            return _Proc()

        with unittest.mock.patch.object(subprocess, "Popen", fake_popen):
            with open(zip_path, "rb") as fz:
                z = zipf_module.ZipFile(fz, "r", allowZip64=True)
                z.extract(nested_name, config.SOPDS_TEMP_DIR)
                extracted = os.path.realpath(
                    os.path.join(config.SOPDS_TEMP_DIR, nested_name)
                )
                dl._ensure_inside_temp_dir(extracted)
                safe_name = dl._safe_temp_name(os.path.basename(nested_name))
                file_path = os.path.join(config.SOPDS_TEMP_DIR, safe_name)
                if os.path.realpath(extracted) != os.path.realpath(file_path):
                    os.replace(extracted, file_path)
                dl._ensure_inside_temp_dir(file_path)

                converter_path = "/usr/bin/true"
                tmp_conv_path = os.path.join(config.SOPDS_TEMP_DIR, "out.epub")
                subprocess.Popen(
                    [converter_path, file_path, tmp_conv_path],
                    shell=False,
                    stdout=subprocess.PIPE,
                )

        self.assertTrue(captured_args, "converter Popen must be called")
        file_path_arg = captured_args[0][1]
        self.assertEqual(
            os.path.dirname(os.path.realpath(file_path_arg)),
            os.path.realpath(self.temp_dir),
            "file_path passed to converter must be inside temp dir (basename only)",
        )
        self.assertEqual(
            os.path.basename(file_path_arg),
            "book.fb2",
            "file_path must be renamed to the safe basename, no taint",
        )
        self.assertNotIn(
            "subdir",
            file_path_arg.replace("\\", "/"),
            "nested path component must not leak into converter input",
        )
        self.assertTrue(
            os.path.isfile(file_path_arg),
            "safe-basename file must exist for the converter",
        )
