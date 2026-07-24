from __future__ import annotations

import re
from typing import Any, BinaryIO

STRIP_SYMBOLS = " »«'\"&\n-.#\\`"


class BookFile:
    def __init__(self, file: BinaryIO, original_filename: str, mimetype: str) -> None:
        self.mimetype = mimetype
        self.original_filename = original_filename
        self.title = original_filename
        self.description: str | None = None
        self.authors: list[dict[str, str]] = []
        self.tags: list[str] = []
        self.series_info: dict[str, Any] | None = None
        self.language_code: str | None = None
        self.docdate = ""

    def extract_cover_memory(self) -> bytes | None:
        return None

    def __set_title__(self, title: str | None) -> None:
        if title and isinstance(title, str):
            title = title.strip()
            if title:
                self.title = title

    def __set_docdate__(self, docdate: str | None) -> None:
        if docdate and isinstance(docdate, str):
            docdate = docdate.strip()
            if docdate:
                self.docdate = docdate

    def __add_author__(self, name: str | None, sortkey: str | None = None) -> None:
        if not name or not isinstance(name, str):
            return
        name = self.__normalise_string__(name)
        if not name:
            return
        sortkey = sortkey.strip() if sortkey else name.split()[-1]
        sortkey = self.__normalise_string__(sortkey)
        if sortkey:
            self.authors.append({"name": name, "sortkey": sortkey.lower()})

    def __add_tag__(self, text: str | None) -> None:
        if text and isinstance(text, str):
            text = text.strip()
            if text:
                self.tags.append(text)

    @staticmethod
    def __normalise_string__(text: str | None) -> str | None:
        return re.sub(r"\s+", " ", text.strip()) if text is not None else None


__all__ = ["BookFile", "STRIP_SYMBOLS"]
