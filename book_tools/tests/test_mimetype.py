# -*- coding: utf-8 -*-

import pytest

from book_tools.format import mime_detector
from book_tools.format.mimetype import Mimetype


@pytest.mark.parametrize(
    "ext,expected",
    [
        ("xml", Mimetype.XML),
        ("fb2", Mimetype.FB2),
        ("epub", Mimetype.EPUB),
        ("mobi", Mimetype.MOBI),
        ("zip", Mimetype.ZIP),
        ("pdf", Mimetype.PDF),
        ("doc", Mimetype.MSWORD),
        ("docx", Mimetype.MSWORD),
        ("djvu", Mimetype.DJVU),
        ("txt", Mimetype.TEXT),
        ("rtf", Mimetype.RTF),
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
        ("book.pdf", Mimetype.PDF),
        ("book.txt", Mimetype.TEXT),
        ("archive.tar.gz", Mimetype.OCTET_STREAM),
    ],
)
def test_file(filename: str, expected: str) -> None:
    assert mime_detector.file(filename) == expected
