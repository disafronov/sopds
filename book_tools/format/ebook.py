from __future__ import annotations

import os
import tempfile
import zipfile
from io import BytesIO
from typing import BinaryIO

import ebookmeta
from lxml import etree

from book_tools.format.bookfile import BookFile
from book_tools.format.mimetype import Mimetype


class EbookMetaBook(BookFile):
    def __init__(self, file: BinaryIO, original_filename: str, mimetype: str) -> None:
        super().__init__(file, original_filename, mimetype)
        self._content = file.read()
        self._cover: bytes | None = None
        suffix = os.path.splitext(original_filename)[1]
        path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                path = temporary.name
                temporary.write(self._content)
            metadata = ebookmeta.get_metadata(path)
        finally:
            if path:
                os.unlink(path)
        self.__set_title__(metadata.title)
        sort_names = metadata.author_sort_list
        for index, author in enumerate(metadata.author_list):
            sort_name = sort_names[index] if index < len(sort_names) else None
            self.__add_author__(author, sort_name)
        for tag in metadata.tag_list:
            self.__add_tag__(tag)
        self.description = metadata.description
        self.language_code = metadata.lang
        if metadata.series:
            self.series_info = {
                "title": metadata.series,
                "index": str(metadata.series_index or ""),
            }
        self._cover = metadata.cover_image_data
        if mimetype == Mimetype.FB2:
            self.__set_docdate__(self._fb2_document_date())
        elif mimetype == Mimetype.EPUB:
            self.__set_docdate__(self._epub_document_date())

    def extract_cover_memory(self) -> bytes | None:
        return self._cover

    def _fb2_document_date(self) -> str | None:
        root = etree.fromstring(self._content)
        dates = root.xpath(
            "//*[local-name()='description']"
            "/*[local-name()='document-info']"
            "/*[local-name()='date']"
        )
        return "".join(dates[0].itertext()) if dates else None

    def _epub_document_date(self) -> str | None:
        with zipfile.ZipFile(BytesIO(self._content)) as archive:
            container = etree.fromstring(archive.read("META-INF/container.xml"))
            rootfiles = container.xpath("//*[local-name()='rootfile']/@full-path")
            if not rootfiles:
                return None
            package = etree.fromstring(archive.read(rootfiles[0]))
        dates = package.xpath("//*[local-name()='metadata']/*[local-name()='date']")
        return dates[0].text if dates else None


class FB2(EbookMetaBook):
    def __init__(self, file: BinaryIO, original_filename: str) -> None:
        super().__init__(file, original_filename, Mimetype.FB2)


class EPub(EbookMetaBook):
    def __init__(self, file: BinaryIO, original_filename: str) -> None:
        super().__init__(file, original_filename, Mimetype.EPUB)


__all__ = ["EPub", "FB2"]
