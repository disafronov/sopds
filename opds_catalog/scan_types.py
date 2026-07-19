"""
Data structures for the scanner multiprocessing pipeline.

Workers parse files and return these objects. The main thread collects
them and writes to the database via Django ORM. No ORM objects or
database imports belong here — these are plain picklable containers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AuthorMeta:
    """Normalized author name, ready for DB insertion."""

    name: str


@dataclass(slots=True)
class SeriesMeta:
    """Book series with optional index number."""

    title: str
    index: int = 0


@dataclass(slots=True)
class BookMeta:
    """
    Parsed metadata for a single book file.

    Produced by worker processes during scan. Consumed by the main thread
    which writes to the database via Django ORM.
    """

    filename: str
    rel_path: str
    ext: str
    title: str
    annotation: str
    docdate: str
    lang: str
    filesize: int
    cat_type: int
    authors: list[AuthorMeta] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    series: list[SeriesMeta] = field(default_factory=list)
    inp_rel_path: str | None = None
    legacy_inp_rel_path: str | None = None


@dataclass(slots=True)
class ParseResult:
    """
    Result of parsing one file (book, ZIP archive, or INPX).

    Returned by worker processes. The main thread drains these and
    writes to the database.
    """

    books: list[BookMeta] = field(default_factory=list)
    bad_books: int = 0
    error: str | None = None


@dataclass(slots=True)
class ContainerEntry:
    """Metadata for a single file inside a container archive (INPX or ZIP).

    Used during the discovery phase: a worker opens the container,
    lists its members, and returns a list of ContainerEntry objects
    without parsing their contents.
    """

    name: str
    size: int


@dataclass(slots=True)
class ContainerDiscovery:
    """Result of discovering entries inside a container archive.

    Returned by discovery worker functions (discover_inpx_entries,
    discover_zip_entries). The main thread uses the entries list
    to submit individual processing tasks to the executor.

    For INPX archives, ``inpx_format`` and ``inpx_folders`` carry
    the parsed ``structure.info`` context needed by downstream
    ``parse_inp_job`` workers.
    """

    entries: list[ContainerEntry]
    inpx_format: list[str] | None = None
    inpx_folders: bool = False
    error: str | None = None
    source_path: str | None = None  # path of the container archive (INPX/ZIP)


@dataclass(slots=True)
class LibraryFile:
    """A parseable file found while discovering one library directory."""

    path: str
    name: str
    kind: str
    size: int


@dataclass(slots=True)
class DirectoryDiscovery:
    """One directory-discovery result returned by a filesystem worker."""

    source_path: str
    directories: list[str] = field(default_factory=list)
    files: list[LibraryFile] = field(default_factory=list)
    error: str | None = None
