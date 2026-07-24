# -*- coding: utf-8 -*-

import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from book_tools import format as fmt
from book_tools.format import create_bookfile
from book_tools.format.bookfile import BookFile
from book_tools.format.epub import EPub
from book_tools.format.fb2 import FB2, FB2Zip
from book_tools.format.fb2sax import FB2sax
from book_tools.format.mimetype import Mimetype
from book_tools.format.mobi import Mobipocket

DATA = Path(__file__).parent.parent.parent / "opds_catalog" / "tests" / "data"


class TestFB2:
    def test_parse_real_fb2(self) -> None:
        with open(DATA / "262001.fb2", "rb") as f:
            content = f.read()
        bf = FB2(BytesIO(content), "262001.fb2")
        assert bf.title == "The Sanctuary Sparrow"
        assert bf.authors
        assert any("Peters" in a["name"] for a in bf.authors)
        bf.__exit__(None, None, None)


class TestFB2Zip:
    def test_parse_single_fb2_in_zip(self) -> None:
        # books.zip contains several fb2 files, but FB2Zip requires exactly one.
        # Build a real single-entry fb2 zip from the test data.
        with open(DATA / "262001.fb2", "rb") as f:
            fb2_content = f.read()
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("262001.fb2", fb2_content)
        buf.seek(0)
        bf = FB2Zip(buf, "book.fb2.zip")
        assert bf.title
        bf.__exit__(None, None, None)

    def test_detect_books_zip_as_zip(self) -> None:
        # books.zip holds several fb2 entries (not a single-entry fb2 zip and
        # no epub mimetype), so detect_mime falls back to the generic ZIP type.
        with open(DATA / "books.zip", "rb") as f:
            content = f.read()
        assert fmt.detect_mime(BytesIO(content), "books.zip") == Mimetype.ZIP


class TestEPub:
    def test_parse_real_epub(self) -> None:
        with open(DATA / "mirer.epub", "rb") as f:
            content = f.read()
        bf = EPub(BytesIO(content), "mirer.epub")
        assert bf.title
        bf.__exit__(None, None, None)

    @pytest.mark.parametrize(
        "entries,match",
        [
            ([], "empty zip archive"),
            ([("mimetype", b"not-an-epub")], "content is incorrect"),
            ([("mimetype", Mimetype.EPUB.encode())], "OPF entry not found"),
        ],
    )
    def test_rejects_invalid_structure(
        self, entries: list[tuple[str, bytes]], match: str
    ) -> None:
        content = BytesIO()
        with zipfile.ZipFile(content, "w") as archive:
            for filename, data in entries:
                archive.writestr(filename, data, compress_type=zipfile.ZIP_STORED)
        content.seek(0)

        with pytest.raises(EPub.StructureException, match=match):
            EPub(content, "invalid.epub")

    def test_records_noncanonical_mimetype_entry(self) -> None:
        content = BytesIO()
        with zipfile.ZipFile(content, "w") as archive:
            archive.writestr("first", b"ignored")
            archive.writestr(
                "mimetype", Mimetype.EPUB, compress_type=zipfile.ZIP_STORED
            )
        content.seek(0)

        with pytest.raises(EPub.StructureException):
            EPub(content, "invalid.epub")

    def test_extract_cover_memory(self) -> None:
        with open(DATA / "mirer.epub", "rb") as f:
            content = f.read()
        bf = EPub(BytesIO(content), "mirer.epub")
        # cover may or may not exist; should not raise
        result = bf.extract_cover_memory()
        assert result is None or isinstance(result, bytes)
        bf.__exit__(None, None, None)


class TestMobipocket:
    def test_parse_real_mobi(self) -> None:
        with open(DATA / "robin_cook.mobi", "rb") as f:
            content = f.read()
        bf = Mobipocket(BytesIO(content), "robin_cook.mobi")
        assert bf.title
        bf.__exit__(None, None, None)

    def test_metadata_and_encryption_info(self, mocker: MockerFixture) -> None:
        parsed = {
            "encryption": "DRM",
            "title": "Title",
            "author": "Author",
            "modificationDate": __import__("datetime").datetime(2024, 1, 2),
            "subject": ["one", "two"],
            "description": "Description",
        }
        mocker.patch("book_tools._vendor.fbreader.mobi.BookMobi", return_value=parsed)

        book = Mobipocket(BytesIO(b"mobi"), "book.mobi")

        assert book.title == "Title"
        assert book.tags == ["one", "two"]
        assert book.get_encryption_info() == {"method": "DRM"}

    def test_extract_cover_memory_returns_none_on_parser_error(
        self, mocker: MockerFixture
    ) -> None:
        parsed = {
            "encryption": "no encryption",
            "title": "Title",
            "author": "Author",
            "modificationDate": __import__("datetime").datetime(2024, 1, 2),
            "subject": [],
            "description": "",
        }
        parser = MagicMock()
        parser.__getitem__.side_effect = parsed.__getitem__
        parser.unpackMobiCover.side_effect = ValueError("bad cover")
        mocker.patch("book_tools._vendor.fbreader.mobi.BookMobi", return_value=parser)
        book = Mobipocket(BytesIO(b"mobi"), "book.mobi")

        assert book.get_encryption_info() == {}
        assert book.extract_cover_memory() is None

    @pytest.mark.parametrize("has_cover", [False, True])
    def test_extract_cover_internal(
        self, mocker: MockerFixture, tmp_path: Path, has_cover: bool
    ) -> None:
        parsed = {
            "encryption": "no encryption",
            "title": "Title",
            "author": "Author",
            "modificationDate": __import__("datetime").datetime(2024, 1, 2),
            "subject": [],
            "description": "",
        }
        parser = MagicMock()
        parser.__getitem__.side_effect = parsed.__getitem__

        def unpack(destination: str) -> None:
            if has_cover:
                Path(destination + "_cover.jpg").write_bytes(b"cover")

        parser.unpackMobi.side_effect = unpack
        mocker.patch("book_tools._vendor.fbreader.mobi.BookMobi", return_value=parser)
        book = Mobipocket(BytesIO(b"mobi"), "book.mobi")

        cover, minified = book.extract_cover_internal(str(tmp_path))

        assert cover == ("bookmobi_cover.jpg" if has_cover else None)
        assert minified is False
        assert (tmp_path / "bookmobi_cover.jpg").exists() is has_cover


class TestFB2sax:
    def test_parse_real_fb2(self) -> None:
        with open(DATA / "262001.fb2", "rb") as f:
            content = f.read()
        bf = FB2sax(BytesIO(content), "262001.fb2")
        assert bf.title == "The Sanctuary Sparrow"
        assert bf.authors
        assert any("Peters" in a["name"] for a in bf.authors)
        bf.__exit__(None, None, None)


class TestCreateBookfile:
    @pytest.mark.parametrize(
        "filename,mimetype,expected_cls",
        [
            ("book.fb2", Mimetype.FB2, FB2sax),
            ("book.epub", Mimetype.EPUB, EPub),
            ("book.mobi", Mimetype.MOBI, Mobipocket),
        ],
    )
    def test_factory(
        self,
        mocker: MockerFixture,
        filename: str,
        mimetype: str,
        expected_cls: type[BookFile],
    ) -> None:
        # create_bookfile relies on constance config for the FB2 backend choice
        # and instantiates the real parser, which would parse the raw bytes.
        # Patch the backends with lightweight stubs to verify dispatch only.
        mocker.patch.object(fmt, "detect_mime", return_value=mimetype)
        mocker.patch("book_tools.format.config").SOPDS_FB2SAX = True
        mocker.patch.object(fmt, "FB2sax", return_value=mocker.Mock(spec=FB2sax))
        mocker.patch.object(fmt, "FB2", return_value=mocker.Mock(spec=FB2))
        mocker.patch.object(fmt, "EPub", return_value=mocker.Mock(spec=EPub))
        mocker.patch.object(
            fmt, "Mobipocket", return_value=mocker.Mock(spec=Mobipocket)
        )
        bf = create_bookfile(BytesIO(b"data"), filename)
        assert isinstance(bf, expected_cls)

    def test_factory_rejects_unsupported_format(self, mocker: MockerFixture) -> None:
        mocker.patch.object(fmt, "detect_mime", return_value=Mimetype.OCTET_STREAM)
        with pytest.raises(Exception, match="is not supported"):
            create_bookfile(BytesIO(b"data"), "book.txt")
