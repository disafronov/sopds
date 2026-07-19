import os
import re
from abc import ABCMeta, abstractmethod
from typing import Any, BinaryIO

from book_tools._vendor.fbreader.util import minify_cover


class BookFile(object):
    __metaclass__ = ABCMeta

    def __init__(self, file: BinaryIO, original_filename: str, mimetype: str) -> None:
        self.file: BinaryIO = file
        self.mimetype = mimetype
        self.original_filename = original_filename
        self.title = original_filename
        self.description: str | None = None
        self.authors: list[dict[str, str]] = []
        self.tags: list[str] = []
        self.series_info: dict[str, Any] | None = None
        self.language_code: str | None = None
        self.issues: list[Any] = []
        self.docdate = ""

    def __enter__(self) -> "BookFile":
        return self

    @abstractmethod
    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: Any,
    ) -> None:
        pass

    def extract_cover(self, working_dir: str) -> str | None:
        cover, minified = self.extract_cover_internal(working_dir)
        if cover and not minified:
            minify_cover(os.path.join(working_dir, cover))
        return cover

    def extract_cover_internal(self, working_dir: str) -> tuple[str | None, bool]:
        return (None, False)

    def extract_cover_memory(self) -> bytes | None:
        return None

    @staticmethod
    def __is_text(text: Any) -> bool:
        return isinstance(text, str)

    def __set_title__(self, title: str | None) -> None:
        if title and BookFile.__is_text(title):
            title = title.strip()
            if title:
                self.title = title

    def __set_docdate__(self, docdate: str | None) -> None:
        if docdate and BookFile.__is_text(docdate):
            docdate = docdate.strip()
            if docdate:
                self.docdate = docdate

    def __add_author__(self, name: str | None, sortkey: str | None = None) -> None:
        if not name or not BookFile.__is_text(name):
            return
        name = BookFile.__normalise_string__(name)
        if not name:
            return
        if sortkey:
            sortkey = sortkey.strip()
        if not sortkey:
            sortkey = name.split()[-1]
        normalised_sortkey = BookFile.__normalise_string__(sortkey)
        if normalised_sortkey is None:
            return
        sortkey = normalised_sortkey.lower()
        self.authors.append({"name": name, "sortkey": sortkey})

    def __add_tag__(self, text: str | None) -> None:
        if text and BookFile.__is_text(text):
            text = text.strip()
            if text:
                self.tags.append(text)

    @staticmethod
    def __normalise_string__(text: str | None) -> str | None:
        if text is None:
            return None
        return re.sub(r"\s+", " ", text.strip())

    def get_encryption_info(self) -> dict[str, Any]:
        return {}

    def repair(self, working_dir: str) -> None:
        pass
