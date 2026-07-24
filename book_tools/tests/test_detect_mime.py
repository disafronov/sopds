# -*- coding: utf-8 -*-

import zipfile
from io import BytesIO

from book_tools.format import detect_mime
from book_tools.format.mimetype import Mimetype


def test_detect_fb2_by_content() -> None:
    fb2_ns = "http://www.gribuser.ru/xml/fictionbook/2.0"
    data = b'<?xml version="1.0"?><FictionBook xmlns="' + fb2_ns.encode() + b'">'
    assert detect_mime(BytesIO(data), "book.fb2") == Mimetype.FB2


def test_detect_epub_by_zip() -> None:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
    buf.seek(0)
    assert detect_mime(buf, "book.epub") == Mimetype.EPUB


def test_detect_mobi_by_magic() -> None:
    data = b"\x00" * 60 + b"BOOKMOBI"
    assert detect_mime(BytesIO(data), "book.bin") == Mimetype.MOBI


def test_detect_xml_generic() -> None:
    data = b'<?xml version="1.0"?><root>not fb2</root>'
    assert detect_mime(BytesIO(data), "data.xml") == Mimetype.XML


def test_detect_unknown() -> None:
    data = b"just plain text content"
    assert detect_mime(BytesIO(data), "file.bin") == Mimetype.OCTET_STREAM
