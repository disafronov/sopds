# -*- coding: utf-8 -*-

import pytest

from opds_catalog.utils import to_ascii, translit


@pytest.mark.parametrize(
    "src,expected",
    [
        ("привет", "privet"),
        ("Привет", "Privet"),
        ("жцчшщюя", "zhtschshschjuja"),
        ("ЖЦЧШЩЮЯ", "ZhTsChShSchJuJa"),
        ("ёжик", "ezhik"),
        ("книга: том 1", "kniga__tom_1"),
        ("текст №5", "tekst_N5"),
    ],
)
def test_translit(src: str, expected: str) -> None:
    assert translit(src) == expected


def test_translit_removes_quotes() -> None:
    assert '"' not in translit('книга "в кавычках"')


def test_translit_assert_on_non_string() -> None:
    with pytest.raises(AssertionError):
        translit(123)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "src,expected",
    [
        ("hello", "hello"),
        ("привет", "??????"),
        ("мир", "???"),
    ],
)
def test_to_ascii(src: str, expected: str) -> None:
    assert to_ascii(src) == expected
