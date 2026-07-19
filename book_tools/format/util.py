"""Compatibility exports for the vendored FBReader implementation."""

from book_tools._vendor.fbreader.util import (
    list_zip_file_infos,
    minify_cover,
    strip_symbols,
)

__all__ = ["list_zip_file_infos", "minify_cover", "strip_symbols"]
