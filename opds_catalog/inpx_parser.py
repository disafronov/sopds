"""
Created on 14 нояб. 2016 г.

@author: Shelepnev, Dmitry
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Callable
from typing import Any

from constance import config

sAuthor = "AUTHOR"
sGenre = "GENRE"
sTitle = "TITLE"
sSeries = "SERIES"
sSerNo = "SERNO"
sFile = "FILE"
sSize = "SIZE"
sLibId = "LIBID"
sDel = "DEL"
sExt = "EXT"
sDate = "DATE"
sLang = "LANG"
sInsNo = "INSNO"
sFolder = "FOLDER"
sLibRate = "LIBRATE"
sKeyWords = "KEYWORDS"


class Inpx:
    def __init__(
        self,
        inpx_file: str,
        append_callback: Callable[[str, str, dict[str, Any]], object],
        inpskip_callback: Callable[
            [str, str, int], object
        ] = lambda _inpx, _inp, size: 0,
    ) -> None:
        self.inpx_file = inpx_file
        self.inpx_catalog = os.path.dirname(inpx_file)
        self.inpx_structure = False
        self.inpx_folders = False
        self.inpx_format: list[str] = []
        self.inpx_archive = False
        self.inpx_arch_fnames: list[str] = []
        self.inpx_encoding = "utf-8"
        self.inpx_separator = b"\x04"
        self.inpx_itemseparator = ":"
        self.append_callback = append_callback
        self.inpskip_callback = inpskip_callback
        self.TEST_ZIP = config.SOPDS_INPX_TEST_ZIP
        self.TEST_FILES = config.SOPDS_INPX_TEST_FILES
        # Legacy aliases assigned by sopdscan (kept for backward compatibility).
        self.INPX_TEST_ZIP = config.SOPDS_INPX_TEST_ZIP
        self.INPX_TEST_FILES = config.SOPDS_INPX_TEST_FILES
        self.error = 0
        # Cache of external zip file existence/contents keyed by absolute path.
        # Eliminates the O(n^2) behaviour where os.path.isfile() and the full
        # zip namelist() were re-read for every book record of an INPX that
        # references the same archive many times (hundreds of thousands of rows).
        self._zip_cache: dict[str, tuple[bool, set[str]]] = {}

    def _get_zip_info(self, zip_file: str) -> tuple[bool, set[str]]:
        """Return ``(exists, names)`` for an external zip, cached per path.

        The cache is lazily populated on the first miss. ``names`` is only
        materialised when the file exists, to avoid wasting work on missing
        archives (it will be an empty set otherwise).
        """
        cached = self._zip_cache.get(zip_file)
        if cached is not None:
            return cached
        exists = os.path.isfile(zip_file)
        names: set[str] = set()
        if exists:
            with zipfile.ZipFile(zip_file, "r") as zf:
                names = set(zf.namelist())
        result = (exists, names)
        self._zip_cache[zip_file] = result
        return result

    def parse(self) -> None:
        with zipfile.ZipFile(self.inpx_file, "r") as finpx:
            filelist = finpx.namelist()
            # здесь читаем формат файлов inp, если есть, если нет, то по умолчанию
            if "structure.info" in filelist:
                self.inpx_structure = True
                with finpx.open("structure.info") as fsds:
                    fsb = str(fsds.read(), "utf-8")
                    self.inpx_format = fsb.split(";")
                self.inpx_folders = sFolder in self.inpx_format
            else:
                self.inpx_format = [
                    sAuthor,
                    sGenre,
                    sTitle,
                    sSeries,
                    sSerNo,
                    sFile,
                    sSize,
                    sLibId,
                    sDel,
                    sExt,
                    sDate,
                    sLang,
                ]

            for inp_file in filelist:
                inp_name, inp_ext = os.path.splitext(inp_file)

                if inp_ext.upper() != ".INP":
                    continue

                if self.inpskip_callback(
                    self.inpx_file, inp_file, finpx.getinfo(inp_file).file_size
                ):
                    continue

                with finpx.open(inp_file) as finp:
                    for line in finp:
                        meta_list = line.split(self.inpx_separator)
                        meta_data: dict[str, Any] = {}

                        if not self.inpx_folders:
                            meta_data[sFolder] = "%s%s" % (inp_name, ".zip")

                        for idx, key in enumerate(self.inpx_format):
                            try:
                                if key in [sAuthor, sGenre, sSeries]:
                                    meta_data[key] = (
                                        meta_list[idx]
                                        .decode("utf-8")
                                        .split(self.inpx_itemseparator)
                                    )
                                else:
                                    meta_data[key] = (
                                        meta_list[idx].decode("utf-8").strip()
                                    )
                            except (IndexError, UnicodeDecodeError):
                                meta_data[key] = ""

                        if meta_data.get(sDel, "").strip() not in ("", "0"):
                            continue

                        self.append_callback(self.inpx_file, inp_name, meta_data)
