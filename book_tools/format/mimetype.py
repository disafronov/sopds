"""MIME types supported by the application."""


class Mimetype:
    OCTET_STREAM = "application/octet-stream"
    XML = "application/xml"
    ZIP = "application/zip"

    EPUB = "application/epub+zip"
    FB2 = "application/fb2+xml"
    FB2_ZIP = "application/fb2+zip"
    MOBI = "application/x-mobipocket-ebook"


__all__ = ["Mimetype"]
