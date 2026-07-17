from __future__ import annotations

import xml.parsers.expat
from typing import BinaryIO


class fb2tag:
    def __init__(self, tags: tuple[str, ...]) -> None:
        self.tags = tags
        self.attrs: dict[str, str] = {}
        self.attrss: list[dict[str, str]] = []
        self.index = -1
        self.size = len(self.tags)
        self.values: list[str] = []
        self.process_value = False
        self.current_value = ""

    def reset(self) -> None:
        self.index = -1
        self.values = []
        self.attrs = {}
        self.attrss = []
        self.process_value = False
        self.current_value = ""

    def tagopen(self, tag: str, attrs: dict[str, str] = {}) -> bool:
        result = False
        if (self.index + 1) < self.size:
            if self.tags[self.index + 1] == tag:
                self.index += 1
        if (self.index + 1) == self.size:
            self.attrs = attrs
            self.attrss.append(attrs)
            result = True
        return result

    def tagclose(self, tag: str) -> None:
        if self.index >= 0:
            if self.tags[self.index] == tag:
                self.index -= 1
                if self.process_value:
                    self.values.append(self.current_value)
                self.process_value = False

    def setvalue(self, value: str) -> None:
        if (self.index + 1) == self.size:
            if self.process_value is False:
                self.current_value = value
                self.process_value = True
            else:
                self.current_value += value

    def getvalue(self) -> list[str]:
        return self.values

    def gettext(self, divider: str = "\n") -> str:
        result = ""
        if len(self.values) > 0:
            result = divider.join(self.values)
        return result

    def getattr(self, attr: str) -> str | None:
        if len(self.attrs) > 0:
            val = self.attrs.get(attr)
        else:
            val = None
        return val

    def getattrs(self, attr: str) -> list[str | None]:
        if len(self.attrss) > 0:
            val = [a.get(attr) for a in self.attrss if attr in a]
        else:
            val = []
        return val


class fb2cover(fb2tag):
    def __init__(self, tags: tuple[str, ...]) -> None:
        self.iscover = False
        self.cover_name = ""
        self._cover_data: list[str] = []
        self.isfind = False
        fb2tag.__init__(self, tags)

    def reset(self) -> None:
        self.iscover = False
        self.cover_name = ""
        self._cover_data = []
        self.isfind = False
        fb2tag.reset(self)

    def tagopen(self, tag: str, attrs: dict[str, str] = {}) -> bool:
        result = fb2tag.tagopen(self, tag, attrs)
        if result:
            idvalue = self.getattr("id")
            if idvalue is not None:
                idvalue = idvalue.lower()
                if idvalue == self.cover_name:
                    self.iscover = True
        return result

    def tagclose(self, tag: str) -> None:
        if self.iscover:
            self.isfind = True
            self.iscover = False
        fb2tag.tagclose(self, tag)

    def setcovername(self, cover_name: str | None) -> None:
        if cover_name is not None and cover_name != "":
            self.cover_name = cover_name

    def add_data(self, data: str) -> None:
        if self.iscover:
            if data != "\\n":
                self._cover_data.append(data)

    @property
    def cover_data(self) -> str:
        return "".join(self._cover_data)

    @cover_data.setter
    def cover_data(self, value: str) -> None:
        self._cover_data = [value]


class fb2parser:
    def __init__(self, readcover: int = 0) -> None:
        self.rc = readcover
        self.author_first = fb2tag(
            ("description", "title-info", "author", "first-name")
        )
        self.author_last = fb2tag(("description", "title-info", "author", "last-name"))
        self.genre = fb2tag(("description", "title-info", "genre"))
        self.lang = fb2tag(("description", "title-info", "lang"))
        self.book_title = fb2tag(("description", "title-info", "book-title"))
        self.annotation = fb2tag(("description", "title-info", "annotation", "p"))
        self.docdate = fb2tag(("description", "document-info", "date"))
        self.series = fb2tag(("description", "title-info", "sequence"))
        if self.rc != 0:
            self.cover_name = fb2tag(("description", "coverpage", "image"))
            self.cover_image = fb2cover(("fictionbook", "binary"))
        self.stoptag = "description"
        self.process_description = True
        self.parse_error = 0
        self.parse_errormsg: str | Exception = ""

    def reset(self) -> None:
        self.process_description = True
        self.parse_error = 0
        self.author_first.reset()
        self.author_last.reset()
        self.genre.reset()
        self.lang.reset()
        self.book_title.reset()
        self.annotation.reset()
        self.series.reset()
        self.docdate.reset()
        if self.rc != 0:
            self.cover_name.reset()
            self.cover_image.reset()

    def start_element(self, name: str, attrs: dict[str, str]) -> None:
        name = name.lower()
        if self.process_description:
            self.author_first.tagopen(name)
            self.author_last.tagopen(name)
            self.genre.tagopen(name)
            self.lang.tagopen(name)
            self.book_title.tagopen(name)
            self.annotation.tagopen(name)
            self.docdate.tagopen(name)
            self.series.tagopen(name, attrs)
            if self.rc != 0:
                if self.cover_name.tagopen(name, attrs):
                    cover_name = self.cover_name.getattr("l:href")
                    if cover_name == "" or cover_name is None:
                        cover_name = self.cover_name.getattr("xlink:href")
                    if (
                        cover_name is not None
                        and len(cover_name) > 0
                        and cover_name[0] == "#"
                    ):
                        cover_name = cover_name.strip("#")
                    else:
                        cover_name = None
                    self.cover_image.setcovername(cover_name)
        if self.rc != 0:
            self.cover_image.tagopen(name, attrs)

    def end_element(self, name: str) -> None:
        name = name.lower()
        if self.process_description:
            self.author_first.tagclose(name)
            self.author_last.tagclose(name)
            self.genre.tagclose(name)
            self.lang.tagclose(name)
            self.book_title.tagclose(name)
            self.annotation.tagclose(name)
            self.docdate.tagclose(name)
            self.series.tagclose(name)
            if self.rc != 0:
                self.cover_name.tagclose(name)
        if self.rc != 0:
            self.cover_image.tagclose(name)
            if self.cover_image.isfind:
                raise StopIteration

        if name == "author":
            if len(self.author_last.getvalue()) > len(self.author_first.getvalue()):
                self.author_first.values.append(" ")
            elif len(self.author_last.getvalue()) < len(self.author_first.getvalue()):
                self.author_last.values.append(" ")

        if name == self.stoptag:
            if self.rc != 0:
                if self.cover_image.cover_name == "":
                    raise StopIteration
                else:
                    self.process_description = False
            else:
                raise StopIteration

    def char_data(self, data: str) -> None:
        if self.process_description:
            self.author_first.setvalue(data)
            self.author_last.setvalue(data)
            self.genre.setvalue(data)
            self.lang.setvalue(data)
            self.book_title.setvalue(data)
            self.annotation.setvalue(data)
            self.docdate.setvalue(data)
        if self.rc != 0:
            self.cover_image.add_data(data)

    def parse(self, f: BinaryIO, hsize: int = 0) -> None:
        self.reset()
        parser = xml.parsers.expat.ParserCreate()
        parser.StartElementHandler = self.start_element
        parser.EndElementHandler = self.end_element
        parser.CharacterDataHandler = self.char_data
        try:
            if hsize == 0:
                parser.Parse(f.read(), True)
            else:
                parser.Parse(f.read(hsize), True)
        except StopIteration:
            pass
        except Exception as err:
            self.parse_errormsg = err
            self.parse_error = 1
