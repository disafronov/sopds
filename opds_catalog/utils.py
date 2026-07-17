from __future__ import annotations

#######################################################################
#
# Вспомогательные функции


def translit(s: str) -> str:
    """Russian translit: converts 'привет'->'privet'"""
    assert (
        s is not str  # type: ignore[comparison-overlap]
    ), "Error: argument MUST be string"

    table1 = str.maketrans(
        "абвгдеёзийклмнопрстуфхъыьэАБВГДЕЁЗИЙКЛМНОПРСТУФХЪЫЬЭ",
        "abvgdeezijklmnoprstufh'y'eABVGDEEZIJKLMNOPRSTUFH'Y'E",
    )
    table2 = {
        "ж": "zh",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ю": "ju",
        "я": "ja",
        "Ж": "Zh",
        "Ц": "Ts",
        "Ч": "Ch",
        "Ш": "Sh",
        "Щ": "Sch",
        "Ю": "Ju",
        "Я": "Ja",
        "«": "",
        "»": "",
        '"': "",
        "\n": "_",
        " ": "_",
        "'": "",
        ":": "_",
        "№": "N",
    }
    s = s.translate(table1)
    for k in table2.keys():
        s = s.replace(k, table2[k])
    return s


def to_ascii(s: str) -> str:
    return s.encode("ascii", "replace").decode("utf-8")
