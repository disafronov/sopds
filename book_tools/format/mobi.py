from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import BinaryIO

import mobi
from lxml import etree

from book_tools.format.bookfile import BookFile
from book_tools.format.mimetype import Mimetype

DC = "http://purl.org/dc/elements/1.1/"
OPF = "http://www.idpf.org/2007/opf"


class Mobipocket(BookFile):
    def __init__(self, file: BinaryIO, original_filename: str) -> None:
        super().__init__(file, original_filename, Mimetype.MOBI)
        self._cover: bytes | None = None
        temporary_dir = ""
        try:
            temporary_dir, _output = mobi.extract(file)
            self._load_metadata(Path(temporary_dir))
        finally:
            if temporary_dir:
                shutil.rmtree(temporary_dir)

    def extract_cover_memory(self) -> bytes | None:
        return self._cover

    def _load_metadata(self, directory: Path) -> None:
        opf_files = sorted(directory.rglob("*.opf"))
        if not opf_files:
            raise ValueError("MOBI metadata not found")
        opf_path = opf_files[0]
        root = etree.parse(str(opf_path)).getroot()
        self.__set_title__(self._text(root, "title"))
        self.language_code = self._text(root, "language")
        self.description = self._text(root, "description")
        self.__set_docdate__(self._text(root, "date"))
        for creator in root.findall(f".//{{{DC}}}creator"):
            self.__add_author__(
                creator.text,
                creator.get(f"{{{OPF}}}file-as"),
            )
        for subject in root.findall(f".//{{{DC}}}subject"):
            self.__add_tag__(subject.text)
        metadata = root.find(f".//{{{OPF}}}metadata")
        if metadata is not None:
            series = self._meta_content(metadata, "calibre:series")
            if series:
                self.series_info = {
                    "title": series,
                    "index": self._meta_content(metadata, "calibre:series_index") or "",
                }
            cover_id = self._meta_content(metadata, "cover")
            if cover_id:
                cover = root.find(
                    f".//{{{OPF}}}manifest/{{{OPF}}}item[@id='{cover_id}']"
                )
                if cover is not None and cover.get("href"):
                    cover_path = (
                        opf_path.parent / os.fspath(cover.get("href"))
                    ).resolve()
                    if (
                        cover_path.is_relative_to(directory.resolve())
                        and cover_path.is_file()
                    ):
                        self._cover = cover_path.read_bytes()

    @staticmethod
    def _text(root: etree._Element, name: str) -> str | None:
        element = root.find(f".//{{{DC}}}{name}")
        return element.text if element is not None else None

    @staticmethod
    def _meta_content(metadata: etree._Element, name: str) -> str | None:
        element = metadata.find(f"{{{OPF}}}meta[@name='{name}']")
        return element.get("content") if element is not None else None


__all__ = ["Mobipocket"]
