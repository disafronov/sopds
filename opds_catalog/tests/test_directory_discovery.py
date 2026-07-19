import os
from typing import Any

from opds_catalog.scan_parser import discover_directory


def test_discover_directory_classifies_tasks(tmp_path: Any) -> None:
    child = tmp_path / "child"
    child.mkdir()
    (tmp_path / "book.fb2").write_bytes(b"book")
    (tmp_path / "archive.zip").write_bytes(b"zip")
    (tmp_path / "ignored.inp").write_bytes(b"inp")

    result = discover_directory(str(tmp_path), (".fb2",), True, True)

    assert result.error is None
    assert result.directories == [str(child)]
    assert {(item.name, item.kind) for item in result.files} == {
        ("book.fb2", "book"),
        ("archive.zip", "zip"),
    }
    assert all(item.size > 0 for item in result.files)


def test_discover_directory_inpx_takes_precedence(tmp_path: Any) -> None:
    (tmp_path / "index.inpx").write_bytes(b"inpx")
    (tmp_path / "books.zip").write_bytes(b"zip")
    (tmp_path / "book.fb2").write_bytes(b"book")

    result = discover_directory(str(tmp_path), (".fb2",), True, True)

    assert [(item.name, item.kind) for item in result.files] == [("index.inpx", "inpx")]


def test_discover_directory_respects_container_flags(tmp_path: Any) -> None:
    (tmp_path / "archive.zip").write_bytes(b"zip")
    (tmp_path / "index.inpx").write_bytes(b"inpx")

    result = discover_directory(str(tmp_path), (".fb2",), False, False)

    assert result.files == []


def test_discover_directory_reports_os_error(tmp_path: Any) -> None:
    missing = os.path.join(str(tmp_path), "missing")

    result = discover_directory(missing, (".fb2",), True, True)

    assert result.error is not None
    assert result.source_path == missing
