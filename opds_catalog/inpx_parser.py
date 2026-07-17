"""
Created on 14 нояб. 2016 г.

@author: Shelepnev, Dmitry
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Callable
from typing import Any

from constance import config  # type: ignore[import-untyped]

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
        ] = lambda inpx, _inp, size: 0,
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

    def parse(self) -> None:
        finpx = zipfile.ZipFile(self.inpx_file, "r")
        filelist = finpx.namelist()
        # здесь читаем формат файлов inp, если есть, если нет, то по умолчанию
        if "structure.info" in filelist:
            self.inpx_structure = True
            fsds = finpx.open("structure.info")
            fsb = str(fsds.read(), "utf-8")
            self.inpx_format = fsb.split(";")
            fsds.close()
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

            finp = finpx.open(inp_file)
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
                                .decode(self.inpx_encoding)
                                .split(self.inpx_itemseparator)
                            )
                            if "" in meta_data[key]:
                                meta_data[key].remove("")
                        else:
                            meta_data[key] = meta_list[idx].decode(self.inpx_encoding)
                    except IndexError:
                        meta_data[key] = ""

                if not (meta_data[sDel].strip() in ["", "0"]):
                    continue

                zip_file = os.path.join(self.inpx_catalog, meta_data[sFolder])
                if (self.TEST_ZIP or self.TEST_FILES) and not os.path.isfile(zip_file):
                    continue

                if self.TEST_FILES:
                    if (
                        not "%s.%s" % (meta_data[sFile], meta_data[sExt])
                        in zipfile.ZipFile(zip_file, "r").namelist()
                    ):
                        continue

                self.append_callback(self.inpx_file, inp_name, meta_data)

            finp.close()
        finpx.close()
