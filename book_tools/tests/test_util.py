# -*- coding: utf-8 -*-

import zipfile
from io import BytesIO
from typing import Any

from book_tools.format.util import list_zip_file_infos, minify_cover


class TestListZipFileInfos:
    def test_lists_files(self) -> None:
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("file1.txt", "c1")
            zf.writestr("dir/file2.txt", "c2")
        buf.seek(0)
        infos = list_zip_file_infos(zipfile.ZipFile(buf))
        names = {i.filename for i in infos}
        assert "file1.txt" in names
        assert "dir/file2.txt" in names

    def test_empty_zip(self) -> None:
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass
        buf.seek(0)
        assert list_zip_file_infos(zipfile.ZipFile(buf)) == []


class TestMinifyCover:
    def test_noop(self, tmp_path: Any) -> None:
        # minify_cover is a no-op stub; should not raise
        minify_cover(str(tmp_path / "nonexistent.png"))
