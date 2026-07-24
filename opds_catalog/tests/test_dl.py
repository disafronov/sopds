import io
import os
import unittest
import unittest.mock
import zipfile
from base64 import b64encode
from typing import cast
from unittest.mock import MagicMock

import pytest
from constance import config
from django.contrib.auth.models import User
from django.http import Http404, HttpRequest, HttpResponse
from django.test import Client
from django.urls import reverse
from PIL import Image
from pytest_mock import MockerFixture

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


class TestGetFileData:
    """dl.getFileData()."""

    def test_cat_normal(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(spec=Book)
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_NORMAL, path=".")
        book.filename = "test.fb2"
        with mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib")):
            m = mocker.mock_open(read_data=b"bookdata")
            mocker.patch("builtins.open", m)
            assert dl.getFileData(book).read() == b"bookdata"

    def test_cat_zip(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(spec=Book)
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_ZIP, path="lib.zip")
        book.filename = "inner.fb2"
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"dummy"))
        mocker.patch(
            "opds_catalog.zipf.ZipFile",
            return_value=mocker.MagicMock(
                open=lambda n: io.BytesIO(b"zipdata"),
            ),
        )
        with mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib")):
            assert dl.getFileData(book).read() == b"zipdata"

    def test_cat_normal_not_found(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(spec=Book)
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_NORMAL, path=".")
        book.filename = "missing.fb2"
        with mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib")):
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
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_NORMAL, path=".")
        with mocker.patch.object(
            dl,
            "config",
            _cfg(SOPDS_TITLE_AS_FILENAME=False),
        ):
            with mocker.patch.object(
                dl,
                "django_settings",
                _cfg(SOPDS_ROOT_LIB="/lib"),
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
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_NORMAL, path=".")
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
            _cfg(SOPDS_AUTH=False, SOPDS_CACHE_TIME=0),
        ):
            with mocker.patch.object(
                dl,
                "django_settings",
                _cfg(SOPDS_ROOT_LIB="/lib"),
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
            _cfg(SOPDS_AUTH=False, SOPDS_CACHE_TIME=0),
        ):
            with mocker.patch.object(
                dl,
                "django_settings",
                _cfg(SOPDS_ROOT_LIB="/lib"),
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
            _cfg(SOPDS_AUTH=False, SOPDS_CACHE_TIME=0),
        ):
            with mocker.patch.object(
                dl,
                "django_settings",
                _cfg(SOPDS_ROOT_LIB="/lib"),
            ):
                with pytest.raises(Http404):
                    dl.Cover(self._request(), 1)


@pytest.mark.django_db
class TestDownloadView(_ViewTestBase):
    """dl.Download view."""

    def _do(self, mocker: MockerFixture, zip_flag: str) -> HttpResponse:
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_NORMAL, path=".")
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
            _cfg(SOPDS_TITLE_AS_FILENAME=False, SOPDS_AUTH=False),
        ):
            with mocker.patch.object(
                dl,
                "django_settings",
                _cfg(SOPDS_ROOT_LIB="/lib"),
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
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_NORMAL, path=".")
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
            _cfg(SOPDS_TITLE_AS_FILENAME=False, SOPDS_AUTH=False),
        ):
            with mocker.patch.object(
                dl,
                "django_settings",
                _cfg(SOPDS_ROOT_LIB="/lib"),
            ):
                with pytest.raises(Http404):
                    dl.Download(self._request("/opds/download/1/0/"), 1, "0")

    def test_bookshelf_is_updated_only_after_success(
        self, mocker: MockerFixture
    ) -> None:
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_NORMAL, path=".")
        book.filename = "missing.fb2"
        book.format = "fb2"
        book.filesize = 100
        book.title = "Book"
        mocker.patch("opds_catalog.models.Book.objects.get", return_value=book)
        mocker.patch("os.path.getsize", return_value=100)
        mocker.patch("builtins.open", side_effect=FileNotFoundError)
        add_to_bookshelf = mocker.patch(
            "opds_catalog.dl.bookshelf.objects.get_or_create"
        )
        request = self._request("/opds/download/1/0/")
        request.user = mocker.MagicMock(is_authenticated=True)
        with mocker.patch.object(
            dl,
            "config",
            _cfg(SOPDS_TITLE_AS_FILENAME=False, SOPDS_AUTH=True),
        ):
            with mocker.patch.object(
                dl,
                "django_settings",
                _cfg(SOPDS_ROOT_LIB="/lib"),
            ):
                with pytest.raises(Http404):
                    dl.Download(request, 1, "0")
        add_to_bookshelf.assert_not_called()

    def test_basic_auth_download_updates_bookshelf(self, mocker: MockerFixture) -> None:
        user = User.objects.create_user(username="reader", password="password")
        book = mocker.MagicMock(spec=Book)
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_NORMAL, path=".")
        book.filename = "book.fb2"
        book.format = "fb2"
        book.filesize = 11
        book.title = "Book"
        mocker.patch("opds_catalog.dl.Book.objects.get", return_value=book)
        mocker.patch("opds_catalog.dl.os.path.getsize", return_value=11)
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"bookcontent"))
        add_to_bookshelf = mocker.patch(
            "opds_catalog.dl.bookshelf.objects.get_or_create"
        )
        mocker.patch.object(
            dl,
            "django_settings",
            _cfg(SOPDS_ROOT_LIB="/lib"),
        )
        original_auth = config.SOPDS_AUTH
        original_title_as_filename = config.SOPDS_TITLE_AS_FILENAME
        config.SOPDS_AUTH = True
        config.SOPDS_TITLE_AS_FILENAME = False
        credentials = b64encode(b"reader:password").decode()

        try:
            response = Client().get(
                reverse("opds:download", args=[1, 0]),
                HTTP_AUTHORIZATION=f"Basic {credentials}",
            )
        finally:
            config.SOPDS_AUTH = original_auth
            config.SOPDS_TITLE_AS_FILENAME = original_title_as_filename

        assert response.status_code == 200
        assert response.content == b"bookcontent"
        add_to_bookshelf.assert_called_once_with(user=user, book=book)


@pytest.mark.django_db
class TestCover0:
    """Tests for Cover0() view — FB2 cover extraction via fb2parse."""

    @pytest.mark.django_db
    def test_returns_cover_for_fb2(self, mocker: MockerFixture) -> None:
        from opds_catalog import dl

        dl_fb2parse = dl.fb2parse  # type: ignore[attr-defined]
        dl_base64 = dl.base64  # type: ignore[attr-defined]
        mock_book = mocker.MagicMock()
        mock_book.catalog.cat_type = "fb2"
        mock_book.format = "fb2"
        mock_book.catalog.path = "/tmp/book.fb2"

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
        mock_book.catalog.cat_type = "fb2"
        mock_book.format = "fb2"
        mock_book.catalog.path = "/tmp/book.fb2"

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
        mock_book.catalog.cat_type = "fb2"
        mock_book.format = "fb2"
        mock_book.catalog.path = "/tmp/book.fb2"

        mocker.patch("opds_catalog.dl.Book.objects.get", return_value=mock_book)
        mock_book_data = mocker.MagicMock()
        mock_book_data.extract_cover_memory.side_effect = Exception("fail")
        mocker.patch("opds_catalog.dl.create_bookfile", return_value=mock_book_data)
        mocker.patch("opds_catalog.dl.os.path.exists", return_value=False)

        request = mocker.MagicMock()
        with pytest.raises(Http404):
            dl.Cover(request, 1, False)
