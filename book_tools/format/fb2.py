"""Compatibility exports for the vendored FBReader implementation."""

from book_tools._vendor.fbreader.fb2 import (
    FB2,
    FB2Base,
    FB2StructureException,
    FB2Zip,
    Namespace,
)

__all__ = ["FB2", "FB2Base", "FB2StructureException", "FB2Zip", "Namespace"]
