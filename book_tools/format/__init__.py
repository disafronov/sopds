from __future__ import annotations

import os
import zipfile
from io import BytesIO
from typing import TYPE_CHECKING, Any, BinaryIO
from xml.sax import handler, parse, xmlreader

from book_tools.format.epub import EPub
from book_tools.format.fb2 import FB2
from book_tools.format.mimetype import Mimetype
from book_tools.format.mobi import Mobipocket

if TYPE_CHECKING:
    from book_tools.format.bookfile import BookFile

SUPPORTED_BOOK_EXTENSIONS = frozenset({".fb2", ".epub", ".mobi"})


def supported_book_extensions(extensions: list[str]) -> tuple[str, ...]:
    return tuple(
        normalized
        for extension in extensions
        if (normalized := extension.lower()) in SUPPORTED_BOOK_EXTENSIONS
    )


class mime_detector:
    @staticmethod
    def fmt(fmt: str) -> str:
        if fmt.lower() == "xml":
            return Mimetype.XML
        elif fmt.lower() == "fb2":
            return Mimetype.FB2
        elif fmt.lower() == "epub":
            return Mimetype.EPUB
        elif fmt.lower() == "mobi":
            return Mimetype.MOBI
        elif fmt.lower() == "zip":
            return Mimetype.ZIP
        else:
            return Mimetype.OCTET_STREAM

    @staticmethod
    def file(filename: str) -> str:
        n, e = os.path.splitext(filename)
        return mime_detector.fmt(e[1:])


def detect_mime(file: BinaryIO, original_filename: str) -> str:
    FB2_ROOT = "FictionBook"
    mime = mime_detector.file(original_filename)

    try:
        if mime == Mimetype.XML:
            if FB2_ROOT == __xml_root_tag(file):
                return Mimetype.FB2
        elif mime == Mimetype.ZIP:
            with zipfile.ZipFile(file) as zip_file:
                if not zip_file.testzip():
                    try:
                        with zip_file.open("mimetype") as mimetype_file:
                            if (
                                mimetype_file.read(30).decode().rstrip("\n\r")
                                == Mimetype.EPUB
                            ):
                                return Mimetype.EPUB
                    except Exception:
                        pass
        elif mime == Mimetype.OCTET_STREAM:
            mobiflag = file.read(68)
            mobiflag = mobiflag[60:]
            if mobiflag.decode() == "BOOKMOBI":
                return Mimetype.MOBI
    except Exception:
        pass

    return mime


def create_bookfile(file: str | BinaryIO, original_filename: str) -> BookFile:
    if isinstance(file, str):
        file = open(file, "rb")
    file = BytesIO(file.read())
    mimetype = detect_mime(file, original_filename)
    if mimetype == Mimetype.EPUB:
        return EPub(file, original_filename)
    elif mimetype == Mimetype.FB2:
        return FB2(file, original_filename)
    elif mimetype == Mimetype.MOBI:
        return Mobipocket(file, original_filename)
    else:
        raise Exception("File type '%s' is not supported, sorry" % mimetype)


def __xml_root_tag(file: Any) -> str | None:
    class XMLRootFound(Exception):
        def __init__(self, name: str) -> None:
            self.name = name

    class RootTagFinder(handler.ContentHandler):
        def startElement(self, name: str, attrs: xmlreader.AttributesImpl) -> None:
            raise XMLRootFound(name)

    try:
        parse(file, RootTagFinder())
    except XMLRootFound as e:
        return e.name
    return None
