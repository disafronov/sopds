"""ZIP support backed by Python's standard library."""

from __future__ import annotations

from os import PathLike
from typing import IO, Literal
from zipfile import (
    ZIP_DEFLATED,
    ZIP_STORED,
    BadZipFile,
)
from zipfile import ZipFile as StandardZipFile
from zipfile import (
    ZipInfo,
    is_zipfile,
)

from constance import config


class ZipFile(StandardZipFile):
    """Open ZIP files using the configured legacy filename encoding."""

    def __init__(
        self,
        file: str | PathLike[str] | IO[bytes],
        mode: Literal["r", "w", "x", "a"] = "r",
        compression: int = ZIP_STORED,
        allowZip64: bool = True,
        compresslevel: int | None = None,
        *,
        strict_timestamps: bool = True,
        metadata_encoding: str | None = None,
    ) -> None:
        if mode == "r" and metadata_encoding is None:
            metadata_encoding = config.SOPDS_ZIPCODEPAGE
        super().__init__(
            file,
            mode,
            compression,
            allowZip64,
            compresslevel,
            strict_timestamps=strict_timestamps,
            metadata_encoding=metadata_encoding,
        )


__all__ = [
    "BadZipFile",
    "ZIP_DEFLATED",
    "ZIP_STORED",
    "ZipFile",
    "ZipInfo",
    "is_zipfile",
]
