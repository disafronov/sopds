from typing import Any

from book_tools.format.bookfile import BookFile


class Dummy(BookFile):
    def __init__(self, file: Any, original_filename: str, mimetype: str) -> None:
        BookFile.__init__(self, file, original_filename, mimetype)

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: Any,
    ) -> None:
        pass
