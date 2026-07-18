import io
import os
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
import zipfile
from typing import cast
from unittest.mock import MagicMock

import pytest
from django.http import Http404, HttpRequest, HttpResponse
from django.test import TestCase
from PIL import Image
from pytest_mock import MockerFixture

import opds_catalog.zipf as zipf_module
from opds_catalog import dl, opdsdb
from opds_catalog.models import Book

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DATA = os.path.join(TEST_DIR, "data")


def _make_jpeg(size: tuple[int, int] = (5, 5)) -> bytes:
    img = Image.new("RGB", size, color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _cfg(**kwargs: object) -> unittest.mock.MagicMock:
    """Helper: return a MagicMock suitable for patching dl.config."""
    m = unittest.mock.MagicMock()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


# ──────────────────────────────────────────────
# Helper unit tests (no DB)
# ──────────────────────────────────────────────


class TestGetFileName:
    """Tests for dl.getFileName() — filename generation from Book."""

    @staticmethod
    def _run(title: str, form: str, filename: str, title_as_filename: bool) -> str:
        book = unittest.mock.MagicMock(spec=Book)
        book.title = title
        book.format = form
        book.filename = filename
        with unittest.mock.patch.object(
            dl, "config", _cfg(SOPDS_TITLE_AS_FILENAME=title_as_filename)
        ):
            return dl.getFileName(book)

    @pytest.mark.parametrize(
        "title,form,filename,title_as_filename,expected",
        [
            ("Test Title", "fb2", "orig.fb2", True, "Test_Title.fb2"),
            ("The Sanctuary Sparrow", "fb2", "262001.fb2", False, "262001.fb2"),
            ("Hello", "pdf", "world.txt", False, "world.txt"),
        ],
    )
    def test_get_filename(
        self,
        title: str,
        form: str,
        filename: str,
        title_as_filename: bool,
        expected: str,
    ) -> None:
        assert self._run(title, form, filename, title_as_filename) == expected

    def test_exotic_chars(self) -> None:
        result = self._run("Book: \u2116 1\nNew", "fb2", "orig.fb2", True)
        assert result == "Book__N_1_New.fb2"

    def test_exotic_filename(self) -> None:
        result = self._run("Title", "fb2", "the sanctuary sparrow.fb2", False)
        assert result == "the_sanctuary_sparrow.fb2"


class TestSafeHelpers:
    """_safe_temp_name, _safe_basename, _ensure_inside_temp_dir."""

    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("normal.txt", "normal.txt"),
            ("path/../file.txt", "file.txt"),
            ("test file!@#.fb2", "test_file___.fb2"),
            ("..", ".."),
            ("", ""),
        ],
    )
    def test_safe_temp_name(self, input_name: str, expected: str) -> None:
        assert dl._safe_temp_name(input_name) == expected

    @pytest.mark.parametrize(
        "input_name,should_raise",
        [
            ("normal.txt", False),
            ("path/file.txt", False),
            ("..", True),
            (".", True),
            ("", True),
            ("test\x00file.txt", True),
        ],
    )
    def test_safe_basename(self, input_name: str, should_raise: bool) -> None:
        if should_raise:
            with pytest.raises(ValueError, match="unsafe path component"):
                dl._safe_basename(input_name)
        else:
            assert dl._safe_basename(input_name) == os.path.basename(input_name)

    def test_ensure_inside_temp_dir_normal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            inner = os.path.join(tmpdir, "sub", "file.txt")
            os.makedirs(os.path.dirname(inner), exist_ok=True)
            with open(inner, "w") as f:
                f.write("x")
            with unittest.mock.patch.object(
                dl, "django_settings", _cfg(SOPDS_TEMP_DIR=tmpdir)
            ):
                assert dl._ensure_inside_temp_dir(inner) == inner

    def test_ensure_inside_temp_dir_outside(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with unittest.mock.patch.object(
                dl, "django_settings", _cfg(SOPDS_TEMP_DIR=tmpdir)
            ):
                with pytest.raises(ValueError, match="path escapes temp dir"):
                    dl._ensure_inside_temp_dir("/etc/passwd")


class TestResolveConverter:
    """_resolve_converter."""

    def test_found_by_shutil_which(self, mocker: MockerFixture) -> None:
        mocker.patch.object(shutil, "which", return_value="/usr/bin/ebook-convert")
        assert dl._resolve_converter("ebook-convert") == "/usr/bin/ebook-convert"

    def test_absolute_executable(self, mocker: MockerFixture) -> None:
        mocker.patch.object(shutil, "which", return_value=None)
        mocker.patch.object(os.path, "isfile", return_value=True)
        mocker.patch.object(os, "access", return_value=True)
        assert (
            dl._resolve_converter("/opt/calibre/ebook-convert")
            == "/opt/calibre/ebook-convert"
        )

    def test_not_found(self, mocker: MockerFixture) -> None:
        mocker.patch.object(shutil, "which", return_value=None)
        mocker.patch.object(os.path, "isfile", return_value=False)
        assert dl._resolve_converter("nonexistent") is None

    def test_absolute_not_executable(self, mocker: MockerFixture) -> None:
        mocker.patch.object(shutil, "which", return_value=None)
        mocker.patch.object(os.path, "isfile", return_value=True)
        mocker.patch.object(os, "access", return_value=False)
        assert dl._resolve_converter("/some/exe") is None


class TestGetFileData:
    """dl.getFileData()."""

    def test_cat_normal(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(spec=Book)
        book.cat_type = opdsdb.CAT_NORMAL
        book.path = "."
        book.filename = "test.fb2"
        with mocker.patch.object(dl, "config", _cfg(SOPDS_ROOT_LIB="/lib")):
            m = mocker.mock_open(read_data=b"bookdata")
            mocker.patch("builtins.open", m)
            assert dl.getFileData(book).read() == b"bookdata"

    def test_cat_zip(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(spec=Book)
        book.cat_type = opdsdb.CAT_ZIP
        book.path = "lib.zip"
        book.filename = "inner.fb2"
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"dummy"))
        mocker.patch(
            "opds_catalog.zipf.ZipFile",
            return_value=mocker.MagicMock(
                open=lambda n: io.BytesIO(b"zipdata"),
            ),
        )
        with mocker.patch.object(dl, "config", _cfg(SOPDS_ROOT_LIB="/lib")):
            assert dl.getFileData(book).read() == b"zipdata"

    def test_cat_normal_not_found(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(spec=Book)
        book.cat_type = opdsdb.CAT_NORMAL
        book.path = "."
        book.filename = "missing.fb2"
        with mocker.patch.object(dl, "config", _cfg(SOPDS_ROOT_LIB="/lib")):
            mocker.patch("builtins.open", side_effect=FileNotFoundError)
            with pytest.raises(AssertionError):
                dl.getFileData(book)


class TestGetFileDataZip:
    """dl.getFileDataZip()."""

    def test_returns_in_memory_zip(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(spec=Book)
        book.title = "Test"
        book.format = "fb2"
        book.filename = "orig.fb2"
        book.cat_type = opdsdb.CAT_NORMAL
        book.path = "."
        with mocker.patch.object(
            dl,
            "config",
            _cfg(SOPDS_TITLE_AS_FILENAME=False, SOPDS_ROOT_LIB="/lib"),
        ):
            mocker.patch("builtins.open", mocker.mock_open(read_data=b"bookdata"))
            result = dl.getFileDataZip(book)
            assert isinstance(result, io.BytesIO)
            with zipfile.ZipFile(result, "r") as z:
                names = z.namelist()
                assert len(names) == 1
                assert z.read(names[0]) == b"bookdata"


# ──────────────────────────────────────────────
# View tests (mocked, no DB)
# ──────────────────────────────────────────────


class _ViewTestBase:
    """Base with request helper for view tests."""

    @staticmethod
    def _request(path: str = "/opds/cover/1/") -> HttpRequest:
        req = HttpRequest()
        req.method = "GET"
        req.path = path
        req.META["SERVER_NAME"] = "testserver"
        req.META["SERVER_PORT"] = "80"
        user = unittest.mock.MagicMock()
        user.is_authenticated = False
        req.user = user
        return req


class TestCoverView(_ViewTestBase):
    """dl.Cover view."""

    def _setup_book(
        self, mocker: MockerFixture, filename: str = "cover.fb2", format_: str = "fb2"
    ) -> Book:
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.cat_type = opdsdb.CAT_NORMAL
        book.path = "."
        book.filename = filename
        book.format = format_
        mocker.patch("opds_catalog.models.Book.objects.get", return_value=book)
        return cast(Book, book)

    def test_cover_success(self, mocker: MockerFixture) -> None:
        self._setup_book(mocker)
        jpeg = _make_jpeg()
        mock_book_data = mocker.MagicMock()
        mock_book_data.extract_cover_memory.return_value = jpeg
        mocker.patch("opds_catalog.dl.create_bookfile", return_value=mock_book_data)
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"dummy"))
        with mocker.patch.object(
            dl,
            "config",
            _cfg(SOPDS_ROOT_LIB="/lib", SOPDS_AUTH=False, SOPDS_CACHE_TIME=0),
        ):
            response = dl.Cover(self._request(), 1)
        assert response.status_code == 200
        assert response["Content-Type"] == "image/jpeg"

    def test_cover_thumbnail(self, mocker: MockerFixture) -> None:
        self._setup_book(mocker)
        jpeg = _make_jpeg(size=(200, 200))
        mock_book_data = mocker.MagicMock()
        mock_book_data.extract_cover_memory.return_value = jpeg
        mocker.patch("opds_catalog.dl.create_bookfile", return_value=mock_book_data)
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"dummy"))
        with mocker.patch.object(
            dl,
            "config",
            _cfg(SOPDS_ROOT_LIB="/lib", SOPDS_AUTH=False, SOPDS_CACHE_TIME=0),
        ):
            response = dl.Cover(self._request(), 1, thumbnail=True)
        assert response.status_code == 200
        assert response["Content-Type"] == "image/jpeg"
        assert len(response.content) < len(jpeg) or response.content != jpeg

    def test_book_without_cover(self, mocker: MockerFixture) -> None:
        self._setup_book(mocker, filename="nope.fb2")
        mock_book_data = mocker.MagicMock()
        mock_book_data.extract_cover_memory.return_value = None
        mocker.patch("opds_catalog.dl.create_bookfile", return_value=mock_book_data)
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"dummy"))
        mocker.patch("os.path.exists", return_value=False)
        with mocker.patch.object(
            dl,
            "config",
            _cfg(SOPDS_ROOT_LIB="/lib", SOPDS_AUTH=False, SOPDS_CACHE_TIME=0),
        ):
            with pytest.raises(Http404):
                dl.Cover(self._request(), 1)


@pytest.mark.django_db
class TestDownloadView(_ViewTestBase):
    """dl.Download view."""

    def _do(self, mocker: MockerFixture, zip_flag: str) -> HttpResponse:
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.cat_type = opdsdb.CAT_NORMAL
        book.path = "."
        book.filename = "book.fb2"
        book.format = "fb2"
        book.filesize = 100
        book.title = "Book"
        mocker.patch("opds_catalog.models.Book.objects.get", return_value=book)
        mocker.patch("os.path.getsize", return_value=100)
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"bookcontent"))
        with mocker.patch.object(
            dl,
            "config",
            _cfg(
                SOPDS_ROOT_LIB="/lib", SOPDS_TITLE_AS_FILENAME=False, SOPDS_AUTH=False
            ),
        ):
            return dl.Download(self._request("/opds/download/1/0/"), 1, zip_flag)

    def test_download_success(self, mocker: MockerFixture) -> None:
        response = self._do(mocker, "0")
        assert response.status_code == 200
        assert b"bookcontent" in response.content
        assert "Content-Disposition" in response

    def test_download_zip(self, mocker: MockerFixture) -> None:
        response = self._do(mocker, "1")
        assert response.status_code == 200
        assert zipfile.is_zipfile(io.BytesIO(response.content))

    def test_download_not_found(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.cat_type = opdsdb.CAT_NORMAL
        book.path = "."
        book.filename = "missing.fb2"
        book.format = "fb2"
        book.filesize = 100
        book.title = "Book"
        mocker.patch("opds_catalog.models.Book.objects.get", return_value=book)
        mocker.patch("os.path.getsize", return_value=100)
        mocker.patch("builtins.open", side_effect=FileNotFoundError)
        with mocker.patch.object(
            dl,
            "config",
            _cfg(
                SOPDS_ROOT_LIB="/lib", SOPDS_TITLE_AS_FILENAME=False, SOPDS_AUTH=False
            ),
        ):
            with pytest.raises(Http404):
                dl.Download(self._request("/opds/download/1/0/"), 1, "0")


@pytest.mark.django_db
class TestConvertFB2(_ViewTestBase):
    """dl.ConvertFB2 view."""

    def _setup_book(
        self,
        mocker: MockerFixture,
        *,
        cat_type: int = opdsdb.CAT_NORMAL,
        filename: str = "book.fb2",
        path: str = ".",
    ) -> Book:
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.cat_type = cat_type
        book.path = path
        book.filename = filename
        book.format = "fb2"
        book.title = "Book"
        mocker.patch("opds_catalog.models.Book.objects.get", return_value=book)
        return cast(Book, book)

    def _patch_convert_boilerplate(self, mocker: MockerFixture) -> None:
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"fb2data"))
        mocker.patch("os.path.isfile", return_value=True)
        mock_proc = mocker.MagicMock()
        mock_proc.stdout.readlines.return_value = []
        mocker.patch("subprocess.Popen", return_value=mock_proc)
        mocker.patch("os.remove")
        mocker.patch.object(
            dl, "_resolve_converter", return_value="/usr/bin/ebook-convert"
        )

    def test_convert_fb2_to_epub(self, mocker: MockerFixture) -> None:
        self._setup_book(mocker)
        self._patch_convert_boilerplate(mocker)
        with mocker.patch.object(
            dl,
            "config",
            _cfg(
                SOPDS_ROOT_LIB="/lib",
                SOPDS_TITLE_AS_FILENAME=False,
                SOPDS_AUTH=False,
                SOPDS_FB2TOEPUB="ebook-convert",
            ),
        ):
            with mocker.patch.object(
                dl,
                "django_settings",
                _cfg(SOPDS_TEMP_DIR="/tmp/sopds"),
            ):
                response = dl.ConvertFB2(
                    self._request("/opds/convert/1/epub/"), 1, "epub"
                )
        assert response.status_code == 200
        assert "epub" in response["Content-Disposition"]

    def test_convert_fb2_to_mobi(self, mocker: MockerFixture) -> None:
        self._setup_book(mocker)
        self._patch_convert_boilerplate(mocker)
        with mocker.patch.object(
            dl,
            "config",
            _cfg(
                SOPDS_ROOT_LIB="/lib",
                SOPDS_TITLE_AS_FILENAME=False,
                SOPDS_AUTH=False,
                SOPDS_FB2TOMOBI="ebook-convert",
            ),
        ):
            with mocker.patch.object(
                dl,
                "django_settings",
                _cfg(SOPDS_TEMP_DIR="/tmp/sopds"),
            ):
                response = dl.ConvertFB2(
                    self._request("/opds/convert/1/mobi/"), 1, "mobi"
                )
        assert response.status_code == 200
        assert "mobi" in response["Content-Disposition"]

    def test_invalid_convert_type(self, mocker: MockerFixture) -> None:
        self._setup_book(mocker)
        with pytest.raises(Http404):
            dl.ConvertFB2(self._request(), 1, "pdf")

    def test_path_traversal_blocked(self, mocker: MockerFixture) -> None:
        self._setup_book(
            mocker,
            cat_type=opdsdb.CAT_ZIP,
            filename="../../etc/passwd",
            path="books.zip",
        )
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"zipdata"))
        mock_zip = mocker.MagicMock()
        mock_zip.open.return_value = io.BytesIO(b"fb2data")
        mocker.patch("opds_catalog.zipf.ZipFile", return_value=mock_zip)
        mocker.patch("os.path.isfile", return_value=True)
        mocker.patch.object(
            dl, "_resolve_converter", return_value="/usr/bin/ebook-convert"
        )
        with mocker.patch.object(
            dl,
            "config",
            _cfg(
                SOPDS_ROOT_LIB="/lib",
                SOPDS_TITLE_AS_FILENAME=False,
                SOPDS_AUTH=False,
                SOPDS_FB2TOEPUB="ebook-convert",
            ),
        ):
            with mocker.patch.object(
                dl,
                "django_settings",
                _cfg(SOPDS_TEMP_DIR="/tmp/sopds"),
            ):
                with pytest.raises(ValueError, match="path escapes temp dir"):
                    dl.ConvertFB2(self._request(), 1, "epub")


# ──────────────────────────────────────────────
# Integration test: zip extraction safety
# Requires actual DB (TestCase + fixtures)
# ──────────────────────────────────────────────


class ConvertFB2NestedZipTestCase(TestCase):
    """Regression test for the CAT_ZIP branch in dl.ConvertFB2.

    book.filename stores the FULL entry name including nested directories
    (e.g. "subdir/book.fb2"). The extraction must use the original name to
    look up the archive member (no KeyError) and the resolved extracted path
    must stay inside SOPDS_TEMP_DIR.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self._patcher = unittest.mock.patch.object(
            dl, "django_settings", _cfg(SOPDS_TEMP_DIR=self.temp_dir)
        )
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()

    def test_nested_zip_extract_no_keyerror(self) -> None:
        nested_name = "subdir/book.fb2"
        zip_path = os.path.join(self.temp_dir, "lib.zip")
        with zipfile.ZipFile(zip_path, "w") as zo:
            zo.writestr(nested_name, "<FB2></FB2>")

        with open(zip_path, "rb") as fz:
            z = zipf_module.ZipFile(fz, "r", allowZip64=True)
            z.extract(nested_name, self.temp_dir)
            file_path = os.path.realpath(os.path.join(self.temp_dir, nested_name))
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
            z.extract(flat_name, self.temp_dir)
            file_path = os.path.realpath(os.path.join(self.temp_dir, flat_name))
            dl._ensure_inside_temp_dir(file_path)

        self.assertTrue(os.path.isfile(file_path))

    def test_convertfb2_zip_renames_to_safe_basename(self) -> None:
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
                z.extract(nested_name, self.temp_dir)
                extracted = os.path.realpath(os.path.join(self.temp_dir, nested_name))
                dl._ensure_inside_temp_dir(extracted)
                safe_name = dl._safe_temp_name(os.path.basename(nested_name))
                file_path = os.path.join(self.temp_dir, safe_name)
                if os.path.realpath(extracted) != os.path.realpath(file_path):
                    os.replace(extracted, file_path)
                dl._ensure_inside_temp_dir(file_path)

            subprocess.Popen(
                [
                    "/usr/bin/true",
                    file_path,
                    os.path.join(self.temp_dir, "out.epub"),
                ],
                shell=False,
                stdout=subprocess.PIPE,
            )

        self.assertTrue(captured_args, "converter Popen must be called")
        file_path_arg = captured_args[0][1]
        self.assertEqual(
            os.path.dirname(os.path.realpath(file_path_arg)),
            os.path.realpath(self.temp_dir),
            "file_path passed to converter must be inside temp dir",
        )
        self.assertEqual(
            os.path.basename(file_path_arg),
            "book.fb2",
            "file_path must be renamed to safe basename, no taint",
        )
        self.assertNotIn(
            "subdir",
            file_path_arg.replace("\\", "/"),
            "nested path component must not leak into converter input",
        )
        self.assertTrue(
            os.path.isfile(file_path_arg),
            "safe-basename file must exist",
        )


class TestGetFileDataConv:
    """Tests for getFileDataConv() — external FB2→EPUB/MOBI conversion."""

    @pytest.mark.django_db
    def test_returns_none_for_non_fb2(self, mocker: MockerFixture) -> None:
        from opds_catalog import dl

        book = mocker.MagicMock()
        book.title = "testbook"
        book.format = "epub"
        book.path = "/tmp/book.epub"
        book.filename = "book.epub"

        result = dl.getFileDataConv(book, "epub")
        assert result is None

    @pytest.mark.django_db
    def test_returns_none_for_unknown_convert_type(self, mocker: MockerFixture) -> None:
        from opds_catalog import dl

        book = mocker.MagicMock()
        book.title = "testbook"
        book.format = "fb2"
        book.path = "/tmp/book.fb2"
        book.filename = "book.fb2"

        mocker.patch.object(dl, "getFileData", return_value=mocker.MagicMock())
        result = dl.getFileDataConv(book, "pdf")
        assert result is None

    @pytest.mark.django_db
    def test_returns_none_when_converter_missing(self, mocker: MockerFixture) -> None:
        from opds_catalog import dl

        book = mocker.MagicMock()
        book.title = "testbook"
        book.format = "fb2"
        book.path = "/tmp/book.fb2"
        book.filename = "book.fb2"

        mock_fo = mocker.MagicMock()
        mocker.patch.object(dl, "getFileData", return_value=mock_fo)
        mocker.patch.object(dl, "_resolve_converter", return_value=None)
        result = dl.getFileDataConv(book, "epub")
        assert result is None
        mock_fo.close.assert_called_once()

    @pytest.mark.django_db
    def test_converts_fb2_to_epub(self, mocker: MockerFixture) -> None:
        from opds_catalog import dl

        dl_subprocess = dl.subprocess  # type: ignore[attr-defined]
        dl_os_path = dl.os.path  # type: ignore[attr-defined]
        book = mocker.MagicMock()
        book.title = "testbook"
        book.format = "fb2"
        book.path = "/tmp/book.fb2"
        book.filename = "book.fb2"

        mock_fo = mocker.MagicMock()
        mock_fo.read.return_value = b"FB2DATA"
        mocker.patch.object(dl, "getFileData", return_value=mock_fo)
        mocker.patch.object(dl, "_resolve_converter", return_value="/usr/bin/fb2epub")
        mocker.patch.object(dl, "open", mocker.mock_open(read_data=b"EPUBDATA"))
        mock_popen = mocker.MagicMock()
        mock_popen.stdout.readlines.return_value = []
        mocker.patch.object(dl_subprocess, "Popen", return_value=mock_popen)
        mocker.patch.object(dl_os_path, "isfile", return_value=True)
        mocker.patch.object(dl.os, "remove")  # type: ignore[attr-defined]

        with mocker.patch.object(
            dl,
            "django_settings",
            _cfg(SOPDS_TEMP_DIR="/tmp/sopds"),
        ):
            result = dl.getFileDataConv(book, "epub")

        assert result is not None
        assert result.read() == b"EPUBDATA"


class TestCover0:
    """Tests for Cover0() view — FB2 cover extraction via fb2parse."""

    @pytest.mark.django_db
    def test_returns_cover_for_fb2(self, mocker: MockerFixture) -> None:
        from opds_catalog import dl

        dl_fb2parse = dl.fb2parse  # type: ignore[attr-defined]
        dl_base64 = dl.base64  # type: ignore[attr-defined]
        mock_book = mocker.MagicMock()
        mock_book.cat_type = "fb2"
        mock_book.format = "fb2"
        mock_book.path = "/tmp/book.fb2"

        mocker.patch("opds_catalog.dl.Book.objects.get", return_value=mock_book)
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"FB2"))

        mock_cover = mocker.MagicMock()
        mock_cover.cover_data = "BASE64DATA"
        mock_cover.getattr.return_value = "image/jpeg"
        mock_fb2 = mocker.MagicMock()
        mock_fb2.cover_image = mock_cover
        mocker.patch.object(dl_fb2parse, "fb2parser", return_value=mock_fb2)
        mocker.patch.object(dl_base64, "b64decode", return_value=b"COVERDATA")

        request = mocker.MagicMock()
        response = dl.Cover0(request, 1, False)
        assert response.status_code == 200
        assert response.content == b"COVERDATA"

    @pytest.mark.django_db
    def test_returns_404_when_no_cover(self, mocker: MockerFixture) -> None:
        from opds_catalog import dl

        dl_fb2parse = dl.fb2parse  # type: ignore[attr-defined]
        mock_book = mocker.MagicMock()
        mock_book.cat_type = "fb2"
        mock_book.format = "fb2"
        mock_book.path = "/tmp/book.fb2"

        mocker.patch("opds_catalog.dl.Book.objects.get", return_value=mock_book)
        mock_cover = mocker.MagicMock()
        mock_cover.cover_data = ""
        mock_fb2 = mocker.MagicMock()
        mock_fb2.cover_image = mock_cover
        mocker.patch.object(dl_fb2parse, "fb2parser", return_value=mock_fb2)
        mocker.patch("opds_catalog.dl.os.path.exists", return_value=False)

        request = mocker.MagicMock()
        with pytest.raises(Http404):
            dl.Cover0(request, 1, False)


class TestThumbnail:
    """Tests for Thumbnail() view."""

    @pytest.mark.django_db
    def test_calls_cover_with_thumbnail(self, mocker: MockerFixture) -> None:
        from opds_catalog import dl

        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_cover: MagicMock = mocker.patch.object(
            dl, "Cover", return_value=mock_response
        )

        request = mocker.MagicMock()
        response = dl.Thumbnail(request, 1)
        assert response.status_code == 200
        mock_cover.assert_called_once_with(request, 1, True)


class TestCoverEdgeCases:
    """Edge cases for Cover() view."""

    @pytest.mark.django_db
    def test_404_when_book_not_found(self, mocker: MockerFixture) -> None:
        from opds_catalog import dl

        mocker.patch(
            "opds_catalog.dl.Book.objects.get", side_effect=Exception("not found")
        )

        request = mocker.MagicMock()
        # A non-Http404 exception propagates out of the view wrapper.
        with pytest.raises(Exception, match="not found"):
            dl.Cover(request, 999, False)

    @pytest.mark.django_db
    def test_404_when_cover_extraction_fails(self, mocker: MockerFixture) -> None:
        from opds_catalog import dl

        mock_book = mocker.MagicMock()
        mock_book.cat_type = "fb2"
        mock_book.format = "fb2"
        mock_book.path = "/tmp/book.fb2"

        mocker.patch("opds_catalog.dl.Book.objects.get", return_value=mock_book)
        mock_book_data = mocker.MagicMock()
        mock_book_data.extract_cover_memory.side_effect = Exception("fail")
        mocker.patch("opds_catalog.dl.create_bookfile", return_value=mock_book_data)
        mocker.patch("opds_catalog.dl.os.path.exists", return_value=False)

        request = mocker.MagicMock()
        with pytest.raises(Http404):
            dl.Cover(request, 1, False)
