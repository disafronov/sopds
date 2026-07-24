# -*- coding: utf-8 -*-

import pytest

from book_tools.format import mime_detector, supported_book_extensions
from book_tools.format.mimetype import Mimetype


@pytest.mark.parametrize(
    "ext,expected",
    [
        ("xml", Mimetype.XML),
        ("fb2", Mimetype.FB2),
        ("epub", Mimetype.EPUB),
        ("mobi", Mimetype.MOBI),
        ("zip", Mimetype.ZIP),
        ("pdf", Mimetype.OCTET_STREAM),
        ("doc", Mimetype.OCTET_STREAM),
        ("docx", Mimetype.OCTET_STREAM),
        ("djvu", Mimetype.OCTET_STREAM),
        ("txt", Mimetype.OCTET_STREAM),
        ("rtf", Mimetype.OCTET_STREAM),
        ("unknown", Mimetype.OCTET_STREAM),
        ("XML", Mimetype.XML),
    ],
)
def test_fmt(ext: str, expected: str) -> None:
    assert mime_detector.fmt(ext) == expected


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("book.fb2", Mimetype.FB2),
        ("book.epub", Mimetype.EPUB),
        ("book.mobi", Mimetype.MOBI),
        ("book.zip", Mimetype.ZIP),
        ("book.pdf", Mimetype.OCTET_STREAM),
        ("book.txt", Mimetype.OCTET_STREAM),
        ("archive.tar.gz", Mimetype.OCTET_STREAM),
    ],
)
def test_file(filename: str, expected: str) -> None:
    assert mime_detector.file(filename) == expected


def test_supported_book_extensions_filters_unparsed_formats() -> None:
    assert supported_book_extensions(".FB2 .pdf .epub .djvu .mobi .txt") == (
        ".fb2",
        ".epub",
        ".mobi",
    )
