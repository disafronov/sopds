# -*- coding: utf-8 -*-

from io import BytesIO
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from book_tools import format as fmt
from book_tools.format import create_bookfile
from book_tools.format.bookfile import BookFile
from book_tools.format.epub import EPub
from book_tools.format.fb2 import FB2
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
        assert bf.tags == ["antique"]
        assert bf.language_code == "en"
        assert bf.docdate == "30.1.2011"
        assert bf.extract_cover_memory()


class TestEPub:
    def test_parse_real_epub(self) -> None:
        with open(DATA / "mirer.epub", "rb") as f:
            content = f.read()
        bf = EPub(BytesIO(content), "mirer.epub")
        assert bf.title == "У меня девять жизней (шф (продолжатели))"
        assert bf.authors == [{"name": "Александр Мирер", "sortkey": "мирер"}]
        assert bf.tags == ["sf"]
        assert bf.language_code == "ru"
        assert bf.docdate == "2015"
        assert bf.series_info == {
            "title": "ШФ (продолжатели)",
            "index": "",
        }
        assert bf.description == "Собрание произведений. Том 2  "
        assert bf.extract_cover_memory()

    def test_rejects_invalid_structure(self) -> None:
        with pytest.raises(Exception):
            EPub(BytesIO(b"not an epub"), "invalid.epub")


class TestMobipocket:
    def test_parse_real_mobi(self) -> None:
        with open(DATA / "robin_cook.mobi", "rb") as f:
            content = f.read()
        bf = Mobipocket(BytesIO(content), "robin_cook.mobi")
        assert bf.title == "Vector"
        assert bf.authors == [{"name": "Robin Cook", "sortkey": "cook"}]
        assert bf.language_code == "en"
        assert "Medical" in bf.tags
        assert bf.docdate == "1999-01-02T00:00:00+00:00"
        assert bf.description
        assert bf.extract_cover_memory()


class TestCreateBookfile:
    @pytest.mark.parametrize(
        "filename,mimetype,expected_cls",
        [
            ("book.fb2", Mimetype.FB2, FB2),
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
        mocker.patch.object(fmt, "detect_mime", return_value=mimetype)
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
