"""
Pure parsing functions for the scanner multiprocessing pipeline.

These functions extract metadata from book files and return BookMeta
objects.  They have NO database dependencies and can run in worker
processes.
"""

from __future__ import annotations

import logging
import os
import zipfile
from typing import Any

from book_tools.format.util import strip_symbols
from opds_catalog import inpx_parser
from opds_catalog.scan_types import (
    AuthorMeta,
    BookMeta,
    ContainerDiscovery,
    ContainerEntry,
    DirectoryDiscovery,
    LibraryFile,
    ParseResult,
    SeriesMeta,
)

# INP record field separator (mirrors inpx_parser.Inpx.inpx_separator).
INPX_RECORD_SEPARATOR = b"\x04"
INPX_ITEM_SEPARATOR = ":"

logger = logging.getLogger(__name__)


def discover_directory(
    path: str,
    book_extensions: tuple[str, ...],
    scan_zip: bool,
    scan_inpx: bool,
) -> DirectoryDiscovery:
    """Discover one directory without involving the orchestrator in filesystem I/O."""
    logger.info("WORKER start discover_directory %s", path)
    result = DirectoryDiscovery(source_path=path)
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=True):
                    result.directories.append(entry.path)
                    continue
                if not entry.is_file(follow_symlinks=True):
                    continue
                extension = os.path.splitext(entry.name)[1].lower()
                if scan_inpx and extension == ".inpx":
                    kind = "inpx"
                elif scan_zip and extension == ".zip":
                    kind = "zip"
                elif extension in book_extensions:
                    kind = "book"
                else:
                    continue
                result.files.append(
                    LibraryFile(
                        path=entry.path,
                        name=entry.name,
                        kind=kind,
                        size=entry.stat(follow_symlinks=True).st_size,
                    )
                )
    except OSError as exc:
        result.error = f"Cannot scan directory {path}: {exc}"
    if any(item.kind == "inpx" for item in result.files):
        # An INPX index describes the book archives next to it. Preserve the
        # legacy scanner rule and do not dispatch those archives separately.
        result.files = [item for item in result.files if item.kind == "inpx"]
    logger.info(
        "WORKER done discover_directory %s directories=%d files=%d err=%s",
        path,
        len(result.directories),
        len(result.files),
        result.error,
    )
    return result


def _normalize_author(author_raw: str) -> str:
    """
    Normalize author name extracted from book metadata.

    Mirrors the logic in ``processfile`` (sopdscan.py:326-336):

    1. Strip ``strip_symbols`` whitespace / punctuation.
    2. If the result contains **no** comma, treat the last whitespace-delimited
       token as the surname and move it to the front
       (``"John Smith"`` → ``"Smith John"``).
    3. Names that already contain a comma are kept as-is after stripping
       (``"Smith, John"`` → ``"Smith, John"``).
    """
    author = author_raw.strip(strip_symbols)
    if author and "," not in author:
        parts = author.split()
        if len(parts) > 1:
            author = " ".join([parts[-1], " ".join(parts[:-1])])
    return author


def _to_bookmeta(
    book_data: Any,
    name: str,
    rel_path: str,
    cat_type: int,
    filesize: int,
) -> BookMeta:
    """
    Convert parsed book data into a :class:`BookMeta` object.

    ``book_data`` is the return value of
    :func:`book_tools.format.create_bookfile` — a :class:`BookFile`
    subclass with these attributes:

    * ``authors`` — ``list[dict]`` where each dict has a ``"name"`` key.
    * ``tags`` — ``list[str]`` of genre / tag strings.
    * ``series_info`` — ``dict | None`` with ``"title"`` and ``"index"`` keys.
    * ``language_code`` — ``str | None``.
    * ``title`` — ``str``.
    * ``description`` — ``str | bytes | None``.
    * ``docdate`` — ``str``.
    """

    # --- authors -----------------------------------------------------------
    authors: list[AuthorMeta] = []
    for entry in getattr(book_data, "authors", []):
        raw_name = entry.get("name", "") if isinstance(entry, dict) else ""
        normalized = _normalize_author(raw_name)
        if normalized:
            authors.append(AuthorMeta(name=normalized))

    # --- genres / tags -----------------------------------------------------
    genres: list[str] = [
        g.lower().strip(strip_symbols)
        for g in getattr(book_data, "tags", [])
        if isinstance(g, str) and g.strip()
    ]

    # --- series ------------------------------------------------------------
    series: list[SeriesMeta] = []
    series_info = getattr(book_data, "series_info", None)
    if isinstance(series_info, dict):
        ser_title = (series_info.get("title") or "").strip()
        if ser_title:
            raw_index = series_info.get("index") or "0"
            index = int(raw_index) if str(raw_index).isdigit() else 0
            series.append(SeriesMeta(title=ser_title, index=index))

    # --- title (fallback → filename without extension) ---------------------
    title_raw = (getattr(book_data, "title", "") or "").strip(strip_symbols)
    title = title_raw if title_raw else os.path.splitext(name)[0]

    # --- annotation / description (may be str or bytes) --------------------
    description_raw = getattr(book_data, "description", None)
    if description_raw:
        if isinstance(description_raw, bytes):
            annotation = description_raw.decode("utf8", errors="replace").strip(
                strip_symbols
            )
        else:
            annotation = str(description_raw).strip(strip_symbols)
    else:
        annotation = ""

    # --- language ----------------------------------------------------------
    lang_raw = getattr(book_data, "language_code", None)
    lang = lang_raw.strip(strip_symbols) if lang_raw else ""

    # --- docdate -----------------------------------------------------------
    docdate = getattr(book_data, "docdate", "") or ""

    return BookMeta(
        filename=name,
        rel_path=rel_path,
        ext=os.path.splitext(name)[1].lstrip(".").lower(),
        title=title,
        annotation=annotation,
        docdate=docdate,
        lang=lang,
        filesize=filesize,
        cat_type=cat_type,
        authors=authors,
        genres=genres,
        series=series,
    )


def inpx_entry_to_bookmeta(
    meta_data: dict[str, Any],
    rel_path: str,
    cat_type: int,
    inp_rel_path: str | None = None,
    legacy_inp_rel_path: str | None = None,
) -> BookMeta:
    """
    Convert an INPX metadata entry into a :class:`BookMeta` object.

    ``meta_data`` is the dict built by :class:`inpx_parser.Inpx` for each
    book record inside an ``.inp`` file.  This function mirrors the exact
    field processing done by ``inpx_callback`` in ``sopdscan.py``.

    The INPX format provides metadata only (no annotation, no series
    indices).  Series serial numbers from ``sSerNo`` are ignored — the
    original callback always passes ``0``.
    """

    name = "%s.%s" % (meta_data[inpx_parser.sFile], meta_data[inpx_parser.sExt])

    # --- title / lang / docdate (all strip_symbols) ------------------------
    title = meta_data[inpx_parser.sTitle].strip(strip_symbols)
    lang = meta_data[inpx_parser.sLang].strip(strip_symbols)
    docdate = meta_data[inpx_parser.sDate].strip(strip_symbols)

    # --- annotation (INPX never provides annotations) ----------------------
    annotation = ""

    # --- authors: replace comma with space, no further normalization -------
    # Matches inpx_callback: a.replace(",", " ")
    authors: list[AuthorMeta] = []
    for a in meta_data[inpx_parser.sAuthor]:
        authors.append(AuthorMeta(name=a.replace(",", " ")))

    # --- genres: lowercase + strip_symbols ---------------------------------
    genres: list[str] = [
        g.lower().strip(strip_symbols) for g in meta_data[inpx_parser.sGenre]
    ]

    # --- series: strip whitespace, index always 0 --------------------------
    # The original callback ignores sSerNo and always passes 0 to addbseries.
    series: list[SeriesMeta] = [
        SeriesMeta(title=s.strip(), index=0) for s in meta_data[inpx_parser.sSeries]
    ]

    # --- filesize (INPX stores size as string, BookMeta expects int) -------
    try:
        filesize = int(meta_data[inpx_parser.sSize])
    except (ValueError, TypeError):
        filesize = 0

    return BookMeta(
        filename=name,
        rel_path=rel_path,
        ext=meta_data[inpx_parser.sExt].lower(),
        title=title,
        annotation=annotation,
        docdate=docdate,
        lang=lang,
        filesize=filesize,
        cat_type=cat_type,
        authors=authors,
        genres=genres,
        series=series,
        inp_rel_path=inp_rel_path,
        legacy_inp_rel_path=legacy_inp_rel_path,
    )


# ---------------------------------------------------------------------------
# Worker functions for multiprocessing (module-level for pickling)
# ---------------------------------------------------------------------------


def parse_book_job(
    raw_bytes: bytes,
    name: str,
    rel_path: str,
    cat_type: int,
) -> ParseResult:
    """Parse a single book file from raw bytes.

    Runs inside a worker process.  ``create_bookfile`` is imported lazily
    to avoid unpickling issues when the worker is spawned rather than forked.
    """
    from io import BytesIO

    from book_tools.format import create_bookfile

    logger.info("WORKER start parse_book_job %s", name)
    res = ParseResult()
    try:
        book_data = create_bookfile(BytesIO(raw_bytes), name)
        filesize = len(raw_bytes)
        res.books.append(_to_bookmeta(book_data, name, rel_path, cat_type, filesize))
    except Exception:
        res.bad_books = 1
    logger.info(
        "WORKER done parse_book_job %s books=%d bad=%d",
        name,
        len(res.books),
        res.bad_books,
    )
    return res


def discover_zip_entries(
    path: str, book_extensions: tuple[str, ...]
) -> ContainerDiscovery:
    """Open a ZIP archive and list its member files (discovery phase).

    Lists parseable book members of the archive as :class:`ContainerEntry`.
    No book bytes are read - this returns metadata only so the main
    thread can fan out per-member parsing tasks.
    """
    from opds_catalog import zipf as zipfile

    logger.info("WORKER start discover_zip_entries %s", path)
    entries: list[ContainerEntry] = []
    try:
        with zipfile.ZipFile(path, "r", allowZip64=True) as zf:
            for info in zf.infolist():
                if os.path.splitext(info.filename)[1].lower() not in book_extensions:
                    continue
                entries.append(ContainerEntry(name=info.filename, size=info.file_size))
    except zipfile.BadZipFile as e:
        return ContainerDiscovery(
            entries=[], error=f"Corrupt ZIP archive: {path}: {e}", source_path=path
        )
    return ContainerDiscovery(entries=entries, source_path=path)


def parse_zip_member_job(path: str, member_name: str, rel_path: str) -> ParseResult:
    """Parse a single member of a ZIP archive (processing phase).

    Opens the archive, reads ``member_name`` as raw bytes and delegates
    to :func:`parse_book_job`.  Malformed members increment ``bad_books``.
    """
    from opds_catalog import zipf as zipfile

    logger.info("WORKER start parse_zip_member_job %s %s", path, member_name)
    res = ParseResult()
    try:
        with zipfile.ZipFile(path, "r", allowZip64=True) as zf:
            try:
                raw = zf.read(member_name)
            except zipfile.BadZipFile:
                res.bad_books += 1
                return res
            # CAT_ZIP = 1
            book_res = parse_book_job(raw, member_name, rel_path, 1)
            res.books.extend(book_res.books)
            res.bad_books += book_res.bad_books
    except zipfile.BadZipFile:
        res.error = f"Corrupt ZIP archive: {path}"
    logger.info(
        "WORKER done parse_zip_member_job %s %s books=%d bad=%d",
        path,
        member_name,
        len(res.books),
        res.bad_books,
    )
    return res


def parse_standalone_book_job(
    path: str,
    name: str,
    rel_path: str,
) -> ParseResult:
    """Parse a single book file from disk.

    Reads the file and delegates to :func:`parse_book_job`.  Used for
    standalone book files discovered during ``os.walk`` (not inside
    ZIP/INPX archives).
    """
    logger.info("WORKER start parse_standalone_book_job %s", path)
    with open(path, "rb") as fh:
        raw = fh.read()
    res = parse_book_job(raw, name, rel_path, 0)  # CAT_NORMAL = 0
    logger.info(
        "WORKER done parse_standalone_book_job %s books=%d bad=%d",
        path,
        len(res.books),
        res.bad_books,
    )
    return res


def discover_inpx_entries(path: str) -> ContainerDiscovery:
    """Open an INPX archive and list its .inp member files (discovery phase).

    Reads ``structure.info`` to capture the INPX format definition, then
    lists all ``.inp`` entries. No book records are parsed — this returns
    metadata only so the main thread can fan out per-entry parsing tasks.
    """
    from opds_catalog import inpx_parser

    logger.info("WORKER start discover_inpx_entries %s", path)
    entries: list[ContainerEntry] = []
    inpx_format: list[str] | None = None
    inpx_folders = False
    try:
        with zipfile.ZipFile(path, "r") as finpx:
            filelist = finpx.namelist()
            if "structure.info" in filelist:
                fsb = str(finpx.open("structure.info").read(), "utf-8")
                inpx_format = fsb.split(";")
                inpx_folders = inpx_parser.sFolder in inpx_format
            for name in filelist:
                if os.path.splitext(name)[1].upper() != ".INP":
                    continue
                entries.append(
                    ContainerEntry(name=name, size=finpx.getinfo(name).file_size)
                )
    except zipfile.BadZipFile as e:
        return ContainerDiscovery(
            entries=[], error=f"Corrupt INPX archive: {path}: {e}"
        )
    logger.info(
        "WORKER done discover_inpx_entries %s entries=%d",
        path,
        len(entries),
    )
    return ContainerDiscovery(
        entries=entries,
        inpx_format=inpx_format,
        inpx_folders=inpx_folders,
        source_path=path,
    )


def parse_inp_job(
    inpx_path: str,
    inp_name: str,
    root_lib: str,
    inpx_format: list[str] | None,
    inpx_folders: bool,
    test_zip: bool,
    test_files: bool,
) -> ParseResult:
    """Parse a single .inp file from an INPX archive (processing phase).

    Opens the INPX archive, reads ONE ``.inp`` member, converts each book
    record to :class:`BookMeta` via :func:`inpx_entry_to_bookmeta`.  The
    ``root_lib`` argument replaces ``settings.SOPDS_ROOT_LIB`` which is
    unavailable in worker processes.

    This is a simplified parser: it does NOT perform the ``_get_zip_info`` /
    ``TEST_ZIP`` / ``TEST_FILES`` external-archive checks (those belong to the
    legacy :func:`parse_inpx_job` and will be removed later).
    """
    from opds_catalog import inpx_parser

    logger.info("WORKER start parse_inp_job %s %s", inpx_path, inp_name)
    res = ParseResult()
    if inpx_format is None:
        inpx_format = [
            inpx_parser.sAuthor,
            inpx_parser.sGenre,
            inpx_parser.sTitle,
            inpx_parser.sSeries,
            inpx_parser.sSerNo,
            inpx_parser.sFile,
            inpx_parser.sSize,
            inpx_parser.sLibId,
            inpx_parser.sDel,
            inpx_parser.sExt,
            inpx_parser.sDate,
            inpx_parser.sLang,
        ]
    try:
        with zipfile.ZipFile(inpx_path, "r") as finpx:
            legacy_inp_rel_path = os.path.relpath(
                os.path.join(os.path.dirname(inpx_path), inp_name), root_lib
            )
            inp_rel_path = os.path.join(os.path.relpath(inpx_path, root_lib), inp_name)
            with finpx.open(inp_name) as finp:
                for line in finp:
                    meta_list = line.split(INPX_RECORD_SEPARATOR)
                    meta_data: dict[str, Any] = {}
                    if not inpx_folders:
                        meta_data[inpx_parser.sFolder] = (
                            "%s.zip" % os.path.splitext(inp_name)[0]
                        )
                    for idx, key in enumerate(inpx_format):
                        try:
                            if key in (
                                inpx_parser.sAuthor,
                                inpx_parser.sGenre,
                                inpx_parser.sSeries,
                            ):
                                meta_data[key] = (
                                    meta_list[idx].decode("utf-8").split(":")
                                )
                                if "" in meta_data[key]:
                                    meta_data[key].remove("")
                            else:
                                meta_data[key] = meta_list[idx].decode("utf-8")
                        except IndexError:
                            meta_data[key] = ""
                    if not (meta_data[inpx_parser.sDel].strip() in ["", "0"]):
                        continue
                    current_rel_path = os.path.join(
                        inp_rel_path, meta_data[inpx_parser.sFolder]
                    )
                    bm = inpx_entry_to_bookmeta(
                        meta_data,
                        current_rel_path,
                        3,
                        inp_rel_path=inp_rel_path,
                        legacy_inp_rel_path=legacy_inp_rel_path,
                    )
                    res.books.append(bm)
    except (zipfile.BadZipFile, KeyError) as e:
        res.error = f"Error parsing INP {inp_name} from {inpx_path}: {e}"
    logger.info(
        "WORKER done parse_inp_job %s %s books=%d bad=%d",
        inpx_path,
        inp_name,
        len(res.books),
        res.bad_books,
    )
    return res
