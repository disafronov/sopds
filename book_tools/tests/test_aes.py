# -*- coding: utf-8 -*-

from typing import Any

from book_tools.format.aes import encrypt


class TestAes:
    def test_encrypt_is_noop(self, tmp_path: Any) -> None:
        # aes.encrypt is a commented-out stub; should not raise
        encrypt("somefile", b"16bytekey!!!!!!", str(tmp_path))
