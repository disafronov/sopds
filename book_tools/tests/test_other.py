# -*- coding: utf-8 -*-

from io import BytesIO

from book_tools.format.mimetype import Mimetype
from book_tools.format.other import Dummy


class TestDummy:
    def test_init(self) -> None:
        d = Dummy(BytesIO(b"data"), "file.bin", Mimetype.OCTET_STREAM)
        assert d.mimetype == Mimetype.OCTET_STREAM
        assert d.original_filename == "file.bin"
        assert d.extract_cover_memory() is None
