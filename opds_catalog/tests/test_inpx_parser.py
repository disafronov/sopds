# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import zipfile
from typing import Any

import pytest
from pytest_mock import MockerFixture

from opds_catalog.inpx_parser import Inpx, sAuthor, sExt, sFile, sTitle


@pytest.fixture
def inpx_archive(tmp_path: Any) -> str:
    """Create a minimal but valid .inpx archive (zip with .inp files)."""
    archive_path = tmp_path / "test.inpx"
    # .inp records separate fields with the record separator \x04; the
    # item separator (":") splits sub-values inside a single field.
    sep = b"\x04"
    # Field values in default format order (AUTHOR..LANG), no key labels.
    values = [
        "Пушкин".encode(),
        "Поэзия".encode(),
        "Евгений Онегин".encode(),
        b"",
        b"",
        b"onegin.fb2",
        b"100",
        b"1",
        b"",
        b"fb2",
        b"",
        b"ru",
    ]
    inp_content = sep.join(values) + sep
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("collection.inp", inp_content)
    return str(archive_path)


@pytest.fixture
def patch_constance(mocker: MockerFixture) -> None:
    mocker.patch(
        "opds_catalog.inpx_parser.config",
        type("C", (), {"SOPDS_INPX_TEST_ZIP": False, "SOPDS_INPX_TEST_FILES": False})(),
    )


class TestInpxInit:
    def test_init_sets_defaults(self, patch_constance: None, inpx_archive: str) -> None:
        calls: list[dict[str, Any]] = []

        def cb(inpx: str, inp: str, d: dict[str, Any]) -> None:
            calls.append(d)

        inpx = Inpx(inpx_archive, cb)
        assert inpx.inpx_file == inpx_archive
        assert inpx.inpx_separator == b"\x04"
        assert inpx.inpx_itemseparator == ":"
        assert inpx.error == 0


class TestInpxParse:
    def test_parse_calls_append_callback(
        self, patch_constance: None, inpx_archive: str
    ) -> None:
        calls: list[dict[str, Any]] = []

        def cb(inpx: str, inp: str, d: dict[str, Any]) -> None:
            calls.append(d)

        inpx = Inpx(inpx_archive, cb)
        inpx.parse()
        assert len(calls) == 1
        book = calls[0]
        assert book[sAuthor] == ["Пушкин"]
        assert book[sTitle] == "Евгений Онегин"
        assert book[sFile] == "onegin.fb2"
        assert book[sExt] == "fb2"

    def test_parse_sets_structure_flags(
        self, patch_constance: None, inpx_archive: str
    ) -> None:
        calls: list[dict[str, Any]] = []

        def cb(inpx: str, inp: str, d: dict[str, Any]) -> None:
            calls.append(d)

        inpx = Inpx(inpx_archive, cb)
        inpx.parse()
        assert inpx.inpx_structure is False
        assert inpx.inpx_folders is False

    def test_parse_with_skip_callback(
        self, patch_constance: None, inpx_archive: str
    ) -> None:
        calls: list[dict[str, Any]] = []
        skips: list[tuple[str, int]] = []

        def cb(inpx: str, inp: str, d: dict[str, Any]) -> None:
            calls.append(d)

        def skip_cb(inpx: str, inp: str, size: int) -> None:
            skips.append((inp, size))

        inpx = Inpx(inpx_archive, cb, skip_cb)
        inpx.parse()
        assert len(calls) == 1
        # skip_callback is called per .inp file
        assert len(skips) >= 1


class TestInpxParseZipCache:
    def test_zip_opened_once_per_file(
        self, mocker: MockerFixture, inpx_archive: str
    ) -> None:
        """Under TEST_FILES each external zip is opened once per path.

        The default INPX format has no FOLDER field, so the folder is derived
        as ``<inp_name>.zip``. Naming the .inp ``ext.inp`` makes both records
        resolve to ``ext.zip``; the zip cache must open that file only once.
        """
        inpx_dir = os.path.dirname(inpx_archive)
        ext_archive = os.path.join(inpx_dir, "ext.zip")
        ext_inp = os.path.join(inpx_dir, "ext.inp")
        sep = b"\x04"
        # One record (default format: AUTHOR..LANG), file=book.fb2, ext=fb2.
        record = sep.join(
            [
                b"A",
                b"G",
                b"T",
                b"",
                b"",
                b"book",
                b"10",
                b"1",
                b"",
                b"fb2",
                b"",
                b"ru",
            ]
        )
        # Two identical records separated by CRLF (the INP record delimiter)
        # so the same external zip is requested twice.
        inp_content = record + b"\r\n" + record + b"\r\n"
        with zipfile.ZipFile(ext_archive, "w") as zf:
            zf.writestr("%s.%s" % ("book", "fb2"), "<fb2/>")
        with zipfile.ZipFile(inpx_archive, "w") as zf:
            zf.writestr(os.path.basename(ext_inp), inp_content)

        mocker.patch(
            "opds_catalog.inpx_parser.config",
            type(
                "C", (), {"SOPDS_INPX_TEST_ZIP": False, "SOPDS_INPX_TEST_FILES": True}
            )(),
        )
        real_zip: Any = zipfile.ZipFile
        zip_open = mocker.patch("opds_catalog.inpx_parser.zipfile.ZipFile")

        def spy(path: str, mode: str = "r", *a: Any, **k: Any) -> Any:
            return real_zip(path, mode, *a, **k)

        zip_open.side_effect = spy

        calls: list[dict[str, Any]] = []

        def cb(inpx: str, inp: str, d: dict[str, Any]) -> None:
            calls.append(d)

        inpx = Inpx(inpx_archive, cb)
        inpx.parse()
        # Both records were emitted (the external zip exists and contains the book).
        assert len(calls) == 2
        # The external zip was opened exactly once despite two records.
        opened = [c.args[0] for c in zip_open.call_args_list if len(c.args) > 0]
        assert ext_archive in opened
        assert opened.count(ext_archive) == 1
