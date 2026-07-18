# -*- coding: utf-8 -*-

from io import BytesIO
from typing import Any

from book_tools.format.bookfile import BookFile
from book_tools.format.mimetype import Mimetype


class ConcreteBookFile(BookFile):
    """Minimal concrete subclass to exercise base-class helpers in tests."""

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: Any,
    ) -> None:
        pass


class TestBookFileBase:
    def test_extract_cover_memory_returns_none(self) -> None:
        bf = ConcreteBookFile(BytesIO(b""), "book.fb2", Mimetype.FB2)
        assert bf.extract_cover_memory() is None

    def test_set_title_strips_whitespace(self) -> None:
        bf = ConcreteBookFile(BytesIO(b""), "book.fb2", Mimetype.FB2)
        bf.__set_title__("  My Book  ")
        assert bf.title == "My Book"

    def test_set_title_none(self) -> None:
        bf = ConcreteBookFile(BytesIO(b""), "book.fb2", Mimetype.FB2)
        bf.__set_title__(None)
        assert bf.title == "book.fb2"

    def test_is_text(self) -> None:
        is_text = ConcreteBookFile._BookFile__is_text  # type: ignore[attr-defined]
        assert is_text("text") is True
        assert is_text(123) is False

    def test_context_manager(self) -> None:
        bf = ConcreteBookFile(BytesIO(b""), "book.fb2", Mimetype.FB2)
        with bf as ctx:
            assert ctx is bf
