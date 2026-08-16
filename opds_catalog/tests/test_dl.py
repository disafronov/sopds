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

    def test_cat_inp(self, mocker: MockerFixture) -> None:
        """CAT_INP: path is split and re-joined to reach the parent zip."""
        book = mocker.MagicMock(spec=Book)
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_INP, path="a/inpx/b/inp")
        book.filename = "inner.fb2"
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"dummy"))
        mocker.patch(
            "opds_catalog.zipf.ZipFile",
            return_value=mocker.MagicMock(
                open=lambda n: io.BytesIO(b"inpdata"),
            ),
        )
        with mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib")):
            assert dl.getFileData(book).read() == b"inpdata"

    def test_cat_inp_not_found(self, mocker: MockerFixture) -> None:
        """CAT_INP: FileNotFoundError is swallowed → AssertionError."""
        book = mocker.MagicMock(spec=Book)
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_INP, path="a/inpx/b/inp")
        book.filename = "missing.fb2"
        with mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib")):
            mocker.patch("builtins.open", side_effect=FileNotFoundError)
            with pytest.raises(AssertionError):
                dl.getFileData(book)

    def test_cat_zip_not_found(self, mocker: MockerFixture) -> None:
        """CAT_ZIP: FileNotFoundError is swallowed → AssertionError."""
        book = mocker.MagicMock(spec=Book)
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_ZIP, path="missing.zip")
        book.filename = "inner.fb2"
        with mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib")):
            mocker.patch("builtins.open", side_effect=FileNotFoundError)
            with pytest.raises(AssertionError):
                dl.getFileData(book)


class TestGetBookAnnotation:
    def test_extracts_annotation(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(spec=Book)
        book.filename = "book.fb2"
        mocker.patch.object(dl, "getFileData", return_value=io.BytesIO(b"book"))
        parsed = mocker.MagicMock(description="Annotation from source")
        create_bookfile = mocker.patch.object(
            dl, "create_bookfile", return_value=parsed
        )

        assert dl.getBookAnnotation(book) == "Annotation from source"
        create_bookfile.assert_called_once()

    def test_returns_none_when_extraction_fails(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(spec=Book)
        mocker.patch.object(dl, "getFileData", side_effect=FileNotFoundError)

        assert dl.getBookAnnotation(book) is None


class TestAnnotationView:
    def test_returns_annotation_from_source(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(annotation="")
        mocker.patch.object(Book.objects, "get", return_value=book)
        mocker.patch.object(dl, "getBookAnnotation", return_value="Source annotation")

        response = dl.Annotation(HttpRequest(), 5)

        assert response.status_code == 200
        assert response.content.decode() == "Source annotation"
        assert response["Content-Type"] == "text/html; charset=utf-8"

    def test_returns_empty_when_no_annotation(self, mocker: MockerFixture) -> None:
        book = mocker.MagicMock(annotation="Stored annotation")
        mocker.patch.object(Book.objects, "get", return_value=book)
        mocker.patch.object(dl, "getBookAnnotation", return_value=None)

        response = dl.Annotation(HttpRequest(), 5)

        assert response.status_code == 200
        assert response.content.decode() == ""
        assert response["Content-Type"] == "text/html; charset=utf-8"


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
                response = dl.Cover(self._request(), 1)
        assert response.status_code == 307
        assert "nocover" in response["Location"]


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
        assert b"bookcontent" in b"".join(
            response.streaming_content  # type: ignore[attr-defined]  # FileResponse
        )
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
        assert (
            b"".join(
                response.streaming_content  # type: ignore[attr-defined]  # FileResponse
            )
            == b"bookcontent"
        )
        add_to_bookshelf.assert_called_once_with(user=user, book=book)


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
    def test_cover_extraction_failure_returns_nocover(
        self, mocker: MockerFixture
    ) -> None:
        from opds_catalog import dl

        mock_book = mocker.MagicMock()
        mock_book.catalog.cat_type = opdsdb.CAT_NORMAL
        mock_book.format = "fb2"
        mock_book.catalog.path = "/tmp/book.fb2"

        mocker.patch("opds_catalog.dl.Book.objects.get", return_value=mock_book)
        mock_book_data = mocker.MagicMock()
        mock_book_data.extract_cover_memory.side_effect = Exception("fail")
        mocker.patch("opds_catalog.dl.create_bookfile", return_value=mock_book_data)
        mocker.patch("opds_catalog.dl.os.path.exists", return_value=False)

        request = mocker.MagicMock()
        response = dl.Cover(request, 1, False)
        assert response.status_code == 307
        assert "nocover" in response["Location"]

    @pytest.mark.django_db
    def test_cover_cat_inp(self, mocker: MockerFixture) -> None:
        """Cover from a CAT_INP archive extracts the cover successfully."""
        from opds_catalog import dl

        mock_book = mocker.MagicMock()
        mock_book.catalog.cat_type = opdsdb.CAT_INP
        mock_book.catalog.path = "inpx/collection.inpx/BookDir/Book.inp"
        mock_book.format = "fb2"

        mocker.patch("opds_catalog.dl.Book.objects.get", return_value=mock_book)
        mock_book_data = mocker.MagicMock()
        mock_book_data.extract_cover_memory.return_value = _make_jpeg()
        mocker.patch("opds_catalog.dl.create_bookfile", return_value=mock_book_data)
        mocker.patch(
            "opds_catalog.zipf.ZipFile",
            return_value=mocker.MagicMock(
                open=lambda n: io.BytesIO(b"zipdata"),
            ),
        )
        mocker.patch("builtins.open", mocker.mock_open())

        request = mocker.MagicMock()
        with mocker.patch.object(
            dl, "config", _cfg(SOPDS_AUTH=False, SOPDS_CACHE_TIME=0)
        ):
            with mocker.patch.object(
                dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib")
            ):
                response = dl.Cover(request, 1, False)
        assert response.status_code == 200
        assert response["Content-Type"] == "image/jpeg"

    @pytest.mark.django_db
    def test_cover_cat_zip(self, mocker: MockerFixture) -> None:
        """Cover from a CAT_ZIP archive extracts the cover successfully."""
        from opds_catalog import dl

        mock_book = mocker.MagicMock()
        mock_book.catalog.cat_type = opdsdb.CAT_ZIP
        mock_book.catalog.path = "books.zip"
        mock_book.format = "fb2"

        mocker.patch("opds_catalog.dl.Book.objects.get", return_value=mock_book)
        mock_book_data = mocker.MagicMock()
        mock_book_data.extract_cover_memory.return_value = _make_jpeg()
        mocker.patch("opds_catalog.dl.create_bookfile", return_value=mock_book_data)
        mocker.patch(
            "opds_catalog.zipf.ZipFile",
            return_value=mocker.MagicMock(
                open=lambda n: io.BytesIO(b"zipdata"),
            ),
        )
        mocker.patch("builtins.open", mocker.mock_open())

        request = mocker.MagicMock()
        with mocker.patch.object(
            dl, "config", _cfg(SOPDS_AUTH=False, SOPDS_CACHE_TIME=0)
        ):
            with mocker.patch.object(
                dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib")
            ):
                response = dl.Cover(request, 1, False)
        assert response.status_code == 200
        assert response["Content-Type"] == "image/jpeg"


# ──────────────────────────────────────────────
# Download: CAT_INP, zip_flag, unknown cat_type
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestDownloadCatInp:
    """Download from a CAT_INP archive."""

    def _request(self, path: str = "/opds/download/1/0/") -> HttpRequest:
        from django.test import RequestFactory

        request = RequestFactory().get(path)
        request.user = MagicMock(is_authenticated=False)
        return request

    def test_download_cat_inp_no_zip(self, mocker: MockerFixture) -> None:
        """CAT_INP, zip_flag='0': streams the file from the parent zip."""
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.catalog = mocker.MagicMock(
            cat_type=opdsdb.CAT_INP, path="inpx/col.inpx/sub/inp"
        )
        book.filename = "inner.fb2"
        book.format = "fb2"
        book.filesize = 100
        book.title = "Book"
        mocker.patch("opds_catalog.models.Book.objects.get", return_value=book)

        zip_content = io.BytesIO()
        with zipfile.ZipFile(zip_content, "w") as zf:
            zf.writestr("inner.fb2", b"inpcontent")
        zip_bytes = zip_content.getvalue()

        fz_mock = mocker.MagicMock()
        fz_mock.read.return_value = zip_bytes
        fo_mock = io.BytesIO(b"inpcontent")
        z_mock = mocker.MagicMock()
        z_mock.open.return_value = fo_mock

        mocker.patch("builtins.open", return_value=fz_mock)
        mocker.patch("opds_catalog.zipf.ZipFile", return_value=z_mock)
        mocker.patch("opds_catalog.dl.bookshelf.objects.get_or_create")
        mocker.patch.object(
            dl, "config", _cfg(SOPDS_TITLE_AS_FILENAME=False, SOPDS_AUTH=False)
        )
        mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib"))

        response = dl.Download(self._request(), 1, "0")
        assert response.status_code == 200
        assert (
            b"".join(
                response.streaming_content  # type: ignore[attr-defined]  # FileResponse
            )
            == b"inpcontent"
        )

    def test_download_cat_inp_zip_flag(self, mocker: MockerFixture) -> None:
        """CAT_INP, zip_flag='1': wraps the content in a zip on the fly."""
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.catalog = mocker.MagicMock(
            cat_type=opdsdb.CAT_INP, path="inpx/col.inpx/sub/inp"
        )
        book.filename = "inner.fb2"
        book.format = "fb2"
        book.filesize = 100
        book.title = "Book"
        mocker.patch("opds_catalog.models.Book.objects.get", return_value=book)

        fo_mock = io.BytesIO(b"inpcontent")
        z_mock = mocker.MagicMock()
        z_mock.open.return_value = fo_mock
        fz_mock = mocker.MagicMock()
        mocker.patch("builtins.open", return_value=fz_mock)
        # Only mock ZipFile for read mode; let write mode create real zips.
        real_zipfile = zipfile.ZipFile

        def _zipfile_side_effect(
            file: object, mode: str = "r", *a: object, **kw: object
        ) -> object:
            if mode == "r":
                return z_mock
            return real_zipfile(file, mode, *a, **kw)  # type: ignore[call-overload]

        mocker.patch("opds_catalog.zipf.ZipFile", side_effect=_zipfile_side_effect)
        mocker.patch("opds_catalog.dl.bookshelf.objects.get_or_create")
        mocker.patch.object(
            dl, "config", _cfg(SOPDS_TITLE_AS_FILENAME=False, SOPDS_AUTH=False)
        )
        mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib"))

        response = dl.Download(self._request(), 1, "1")
        assert response.status_code == 200
        buf = response.content
        with zipfile.ZipFile(io.BytesIO(buf)) as zf:
            assert len(zf.namelist()) == 1

    def test_download_unknown_cat_type(self, mocker: MockerFixture) -> None:
        """Unknown cat_type → Http404."""
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.catalog = mocker.MagicMock(cat_type=99, path=".")
        book.filename = "book.fb2"
        book.format = "fb2"
        book.filesize = 100
        book.title = "Book"
        mocker.patch("opds_catalog.models.Book.objects.get", return_value=book)
        mocker.patch.object(
            dl, "config", _cfg(SOPDS_TITLE_AS_FILENAME=False, SOPDS_AUTH=False)
        )
        mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib"))
        with pytest.raises(Http404):
            dl.Download(self._request(), 1, "0")

    def test_download_cat_zip_zip_flag(self, mocker: MockerFixture) -> None:
        """CAT_ZIP, zip_flag='1': wraps zip content in another zip."""
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_ZIP, path="lib.zip")
        book.filename = "inner.fb2"
        book.format = "fb2"
        book.filesize = 100
        book.title = "Book"
        mocker.patch("opds_catalog.models.Book.objects.get", return_value=book)

        fo_mock = io.BytesIO(b"zipdata")
        z_mock = mocker.MagicMock()
        z_mock.open.return_value = fo_mock
        fz_mock = mocker.MagicMock()
        mocker.patch("builtins.open", return_value=fz_mock)
        real_zipfile = zipfile.ZipFile

        def _zipfile_side_effect(
            file: object, mode: str = "r", *a: object, **kw: object
        ) -> object:
            if mode == "r":
                return z_mock
            return real_zipfile(file, mode, *a, **kw)  # type: ignore[call-overload]

        mocker.patch("opds_catalog.zipf.ZipFile", side_effect=_zipfile_side_effect)
        mocker.patch("opds_catalog.dl.bookshelf.objects.get_or_create")
        mocker.patch.object(
            dl, "config", _cfg(SOPDS_TITLE_AS_FILENAME=False, SOPDS_AUTH=False)
        )
        mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib"))

        response = dl.Download(self._request(), 1, "1")
        assert response.status_code == 200
        buf = response.content
        with zipfile.ZipFile(io.BytesIO(buf)) as zf:
            assert len(zf.namelist()) == 1

    def test_download_cat_normal_zip_flag(self, mocker: MockerFixture) -> None:
        """CAT_NORMAL, zip_flag='1': wraps file content in a zip."""
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
        mocker.patch("opds_catalog.dl.bookshelf.objects.get_or_create")
        mocker.patch.object(
            dl, "config", _cfg(SOPDS_TITLE_AS_FILENAME=False, SOPDS_AUTH=False)
        )
        mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib"))

        response = dl.Download(self._request(), 1, "1")
        assert response.status_code == 200
        buf = response.content
        with zipfile.ZipFile(io.BytesIO(buf)) as zf:
            assert len(zf.namelist()) == 1

    def test_download_title_as_filename(self, mocker: MockerFixture) -> None:
        """SOPDS_TITLE_AS_FILENAME uses book.title for the download name."""
        book = mocker.MagicMock(spec=Book)
        book.id = 1
        book.catalog = mocker.MagicMock(cat_type=opdsdb.CAT_NORMAL, path=".")
        book.filename = "orig.fb2"
        book.format = "fb2"
        book.filesize = 100
        book.title = "My Book"
        mocker.patch("opds_catalog.models.Book.objects.get", return_value=book)
        mocker.patch("os.path.getsize", return_value=100)
        mocker.patch("builtins.open", mocker.mock_open(read_data=b"bookcontent"))
        mocker.patch("opds_catalog.dl.bookshelf.objects.get_or_create")
        mocker.patch.object(
            dl, "config", _cfg(SOPDS_TITLE_AS_FILENAME=True, SOPDS_AUTH=False)
        )
        mocker.patch.object(dl, "django_settings", _cfg(SOPDS_ROOT_LIB="/lib"))

        response = dl.Download(self._request(), 1, "0")
        assert response.status_code == 200
        assert "My_Book.fb2" in response["Content-Disposition"]
