# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime
import logging
import multiprocessing
import os
import time
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ProcessPoolExecutor,
    wait,
)
from typing import Any

from constance import config
from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

import opds_catalog.zipf as zipfile
from book_tools.format import create_bookfile
from book_tools.format.util import strip_symbols
from opds_catalog import fb2parse, opdsdb
from opds_catalog.models import (
    SIZE_AUTHOR_NAME,
    SIZE_BOOK_ANNOTATION,
    SIZE_BOOK_DOCDATE,
    SIZE_BOOK_FILENAME,
    SIZE_BOOK_FORMAT,
    SIZE_BOOK_LANG,
    SIZE_BOOK_PATH,
    SIZE_BOOK_TITLE,
    SIZE_GENRE,
    SIZE_GENRE_SUBSECTION,
    SIZE_SERIES,
    Author,
    Book,
    Catalog,
    Genre,
    Series,
    bauthor,
    bgenre,
    bseries,
)
from opds_catalog.scan_types import (
    BookMeta,
    ContainerDiscovery,
    DirectoryDiscovery,
    ParseResult,
)
from opds_catalog.worker_init import init_worker

logger = logging.getLogger(__name__)

# Per-scan memo caches for get_or_create lookups.  Populated by
# store_result() in the main thread.  Cleared at the start of each
# scan by clear_scan_caches().
_author_cache: dict[str, Author] = {}
_genre_cache: dict[str, Genre] = {}
_series_cache: dict[str, Series] = {}


def create_scan_executor(max_workers: int | None) -> ProcessPoolExecutor:
    """Create the production spawn-based scanner process pool."""
    return ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=init_worker,
    )


def clear_scan_caches() -> None:
    """Drop per-scan memo caches. Call at the start of each scan."""
    _author_cache.clear()
    _genre_cache.clear()
    _series_cache.clear()


def store_result(
    result: ParseResult,
    scanner: opdsScanner,
) -> None:
    """Write one worker result as a single database batch."""
    _store_books_batch(result.books, scanner)
    scanner.bad_books += result.bad_books


def _book_key(meta: BookMeta) -> tuple[str, str]:
    return (
        meta.filename[:SIZE_BOOK_FILENAME],
        meta.rel_path[:SIZE_BOOK_PATH],
    )


@transaction.atomic
def _store_books_batch(books: list[BookMeta], scanner: opdsScanner) -> None:
    """Store one bounded batch using bulk operations for rows and M2M links."""
    if not books:
        return

    requested_keys = {_book_key(meta) for meta in books}
    fallback_keys = {
        (meta.filename[:SIZE_BOOK_FILENAME], path[:SIZE_BOOK_PATH])
        for meta in books
        for path in (meta.inp_rel_path, meta.legacy_inp_rel_path)
        if path
    }
    lookup_keys = requested_keys | fallback_keys
    filenames = {filename for filename, _path in lookup_keys}
    paths = {path for _filename, path in lookup_keys}
    existing_books = [
        book
        for book in Book.objects.filter(filename__in=filenames, path__in=paths)
        if (book.filename, book.path) in lookup_keys
    ]
    existing_by_key = {(book.filename, book.path): book for book in existing_books}

    catalogs: dict[tuple[str, int], Catalog] = {}
    migrated_books: list[Book] = []
    existing_keys: set[tuple[str, str]] = set()
    for meta in books:
        key = _book_key(meta)
        book = existing_by_key.get(key)
        if book is None:
            for path in (meta.inp_rel_path, meta.legacy_inp_rel_path):
                if path:
                    book = existing_by_key.get(
                        (meta.filename[:SIZE_BOOK_FILENAME], path[:SIZE_BOOK_PATH])
                    )
                if book is not None:
                    break
        if book is None:
            continue
        existing_keys.add(key)
        if book.path != key[1]:
            catalog_key = (meta.rel_path, meta.cat_type)
            if catalog_key not in catalogs:
                catalogs[catalog_key] = opdsdb.addcattree(meta.rel_path, meta.cat_type)
            book.path = key[1]
            book.catalog = catalogs[catalog_key]
            book.cat_type = meta.cat_type
        book.avail = 2
        migrated_books.append(book)

    if migrated_books:
        Book.objects.bulk_update(
            migrated_books, ["path", "catalog", "cat_type", "avail"]
        )

    new_meta: list[BookMeta] = []
    seen_keys = set(existing_keys)
    for meta in books:
        key = _book_key(meta)
        if key in seen_keys:
            scanner.books_skipped += 1
            continue
        seen_keys.add(key)
        new_meta.append(meta)

    if not new_meta:
        return

    for meta in new_meta:
        catalog_key = (meta.rel_path, meta.cat_type)
        if catalog_key not in catalogs:
            catalogs[catalog_key] = opdsdb.addcattree(meta.rel_path, meta.cat_type)

    author_names = {
        author.name[:SIZE_AUTHOR_NAME] for meta in new_meta for author in meta.authors
    }
    genre_names = {genre[:SIZE_GENRE] for meta in new_meta for genre in meta.genres}
    series_names = {
        series.title[:SIZE_SERIES] for meta in new_meta for series in meta.series
    }

    authors = {
        author.full_name: author
        for author in Author.objects.filter(full_name__in=author_names)
    }
    missing_authors = [
        Author(
            full_name=name,
            search_full_name=name.upper()[:SIZE_AUTHOR_NAME],
            lang_code=opdsdb.getlangcode(name),
        )
        for name in author_names - authors.keys()
    ]
    Author.objects.bulk_create(missing_authors)
    authors.update({author.full_name: author for author in missing_authors})
    _author_cache.update(authors)

    genres = {
        genre.genre: genre for genre in Genre.objects.filter(genre__in=genre_names)
    }
    missing_genres = [
        Genre(
            genre=name,
            section=opdsdb.unknown_genre,
            subsection=name[:SIZE_GENRE_SUBSECTION],
        )
        for name in genre_names - genres.keys()
    ]
    Genre.objects.bulk_create(missing_genres)
    genres.update({genre.genre: genre for genre in missing_genres})
    _genre_cache.update(genres)

    series_by_name = {
        item.ser: item for item in Series.objects.filter(ser__in=series_names)
    }
    missing_series = [
        Series(
            ser=name,
            search_ser=name.upper()[:SIZE_SERIES],
            lang_code=opdsdb.getlangcode(name),
        )
        for name in series_names - series_by_name.keys()
    ]
    Series.objects.bulk_create(missing_series)
    series_by_name.update({item.ser: item for item in missing_series})
    _series_cache.update(series_by_name)

    book_rows = [
        Book(
            filename=meta.filename[:SIZE_BOOK_FILENAME],
            path=meta.rel_path[:SIZE_BOOK_PATH],
            catalog=catalogs[(meta.rel_path, meta.cat_type)],
            filesize=meta.filesize,
            format=meta.ext.lower()[:SIZE_BOOK_FORMAT],
            title=meta.title[:SIZE_BOOK_TITLE],
            search_title=meta.title.upper()[:SIZE_BOOK_TITLE],
            annotation=opdsdb.p(meta.annotation, SIZE_BOOK_ANNOTATION),
            docdate=meta.docdate[:SIZE_BOOK_DOCDATE],
            lang=meta.lang[:SIZE_BOOK_LANG],
            cat_type=meta.cat_type,
            avail=2,
            lang_code=opdsdb.getlangcode(meta.title),
        )
        for meta in new_meta
    ]
    Book.objects.bulk_create(book_rows)

    author_links: list[bauthor] = []
    genre_links: list[bgenre] = []
    series_links: list[bseries] = []
    for meta, book in zip(new_meta, book_rows, strict=True):
        author_links.extend(
            bauthor(book=book, author=authors[item.name[:SIZE_AUTHOR_NAME]])
            for item in meta.authors
        )
        genre_links.extend(
            bgenre(book=book, genre=genres[name[:SIZE_GENRE]]) for name in meta.genres
        )
        series_links.extend(
            bseries(
                book=book,
                ser=series_by_name[item.title[:SIZE_SERIES]],
                ser_no=item.index,
            )
            for item in meta.series
        )

    bauthor.objects.bulk_create(author_links)
    bgenre.objects.bulk_create(genre_links)
    bseries.objects.bulk_create(series_links)
    scanner.books_added += len(book_rows)
    scanner.books_in_archives += sum(meta.cat_type != 0 for meta in new_meta)


class opdsScanner:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.fb2parser: Any = None
        self.init_parser()

        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger("")
            self.logger.setLevel(logging.CRITICAL)
        self.init_stats()

    def init_stats(self) -> None:
        self.t1 = datetime.timedelta(seconds=time.time())
        self.t2 = self.t1
        self.t3 = self.t1
        self.books_added = 0
        self.books_skipped = 0
        self.books_deleted: int | tuple[int, dict[str, int]] = 0
        self.catalogs_deleted = 0
        self.arch_scanned = 0
        self.arch_skipped = 0
        self.bad_archives = 0
        self.bad_books = 0
        self.books_in_archives = 0
        self.inp_cat: Any = None
        self.zip_file: Any = None
        self.rel_path: str | None = None

    def init_parser(self) -> None:
        self.fb2parser = fb2parse.fb2parser(False)

    def log_options(self) -> None:
        self.logger.info(" ***** Starting sopds-scan...")
        self.logger.debug("OPTIONS SET")
        if settings.SOPDS_ROOT_LIB is not None:
            self.logger.debug("root_lib = %s" % settings.SOPDS_ROOT_LIB)
        if config.SOPDS_FB2TOEPUB is not None:
            self.logger.debug("fb2toepub = %s" % config.SOPDS_FB2TOEPUB)
        if config.SOPDS_FB2TOMOBI is not None:
            self.logger.debug("fb2tomobi = %s" % config.SOPDS_FB2TOMOBI)
        if settings.SOPDS_TEMP_DIR is not None:
            self.logger.debug("temp_dir = %s" % settings.SOPDS_TEMP_DIR)
        if config.SOPDS_FB2SAX is not None:
            self.logger.info("FB2SAX = %s" % config.SOPDS_FB2SAX)

    def log_stats(self) -> None:
        self.t2 = datetime.timedelta(seconds=time.time())
        self.logger.info("Books added      : " + str(self.books_added))
        self.logger.info("Books skipped    : " + str(self.books_skipped))
        self.logger.info("Bad books        : " + str(self.bad_books))
        if config.SOPDS_DELETE_LOGICAL:
            self.logger.info("Books deleted    : " + str(self.books_deleted))
        else:
            self.logger.info("Books DB entries deleted : " + str(self.books_deleted))
        self.logger.info("Catalogs deleted : " + str(self.catalogs_deleted))
        self.logger.info("Books in archives: " + str(self.books_in_archives))
        self.logger.info("Archives scanned : " + str(self.arch_scanned))
        self.logger.info("Archives skipped : " + str(self.arch_skipped))
        self.logger.info("Bad archives     : " + str(self.bad_archives))

        t = self.t2 - self.t1
        seconds = t.seconds % 60
        minutes = ((t.seconds - seconds) // 60) % 60
        hours = t.seconds // 3600
        self.logger.info(
            "Time estimated:"
            + str(hours)
            + " hours, "
            + str(minutes)
            + " minutes, "
            + str(seconds)
            + " seconds."
        )

    def scan_all(self) -> None:
        """Scan the book library using a process pool for file parsing.

        Directory discovery and file parsing run in worker processes.
        The main process only schedules follow-up tasks and serializes
        database writes to avoid duplicate rows and connection sharing.
        """
        from opds_catalog.scan_parser import (
            discover_directory,
            discover_inpx_entries,
            discover_zip_entries,
            parse_inp_job,
            parse_standalone_book_job,
            parse_zip_member_job,
        )

        self.init_stats()
        opdsdb.clear_cat_cache()
        clear_scan_caches()
        self.log_options()
        self.inp_cat = None
        self.zip_file = None
        self.rel_path = None

        opdsdb.avail_check_prepare()

        max_workers = settings.SOPDS_SCAN_WORKERS or os.cpu_count()
        self.logger.info("Scanner worker processes: %s", max_workers)
        book_extensions = tuple(config.SOPDS_BOOK_EXTENSIONS.lower().split())

        with create_scan_executor(max_workers) as executor:
            all_futures: set[Future[Any]] = {
                executor.submit(
                    discover_directory,
                    settings.SOPDS_ROOT_LIB,
                    book_extensions,
                    config.SOPDS_ZIPSCAN,
                    config.SOPDS_INPX_ENABLE,
                )
            }

            while all_futures:
                done, all_futures = wait(all_futures, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        result = future.result()
                    except Exception:
                        self.logger.exception("Worker process failed")
                        self.bad_archives += 1
                        continue

                    if isinstance(result, DirectoryDiscovery):
                        logger.info(
                            "RESULT discover_directory source=%s "
                            "dirs=%d files=%d err=%s",
                            result.source_path,
                            len(result.directories),
                            len(result.files),
                            result.error,
                        )
                        if result.error:
                            self.logger.error(result.error)
                            self.bad_archives += 1
                            continue
                        for directory in result.directories:
                            all_futures.add(
                                executor.submit(
                                    discover_directory,
                                    directory,
                                    book_extensions,
                                    config.SOPDS_ZIPSCAN,
                                    config.SOPDS_INPX_ENABLE,
                                )
                            )
                        for discovered_file in result.files:
                            file = discovered_file.path
                            if discovered_file.kind == "inpx":
                                rel_file = os.path.relpath(
                                    file, settings.SOPDS_ROOT_LIB
                                )
                                inpx_size = discovered_file.size

                                if (
                                    config.SOPDS_INPX_SKIP_UNCHANGED
                                    and opdsdb.inpx_skip(rel_file, inpx_size)
                                ):
                                    self.logger.info(
                                        "Skip INPX file = " + file + ". Not changed."
                                    )
                                    continue

                                self.logger.info("Start discovery INPX file = " + file)
                                opdsdb.addcattree(rel_file, opdsdb.CAT_INPX, inpx_size)
                                logger.info(
                                    "DISPATCH discover_inpx_entries inpx=%s", file
                                )
                                all_futures.add(
                                    executor.submit(discover_inpx_entries, file)
                                )
                            elif discovered_file.kind == "zip":
                                rel_file = os.path.relpath(
                                    file, settings.SOPDS_ROOT_LIB
                                )
                                zsize = discovered_file.size

                                if opdsdb.arc_skip(rel_file, zsize):
                                    self.arch_skipped += 1
                                    self.logger.debug(
                                        "Skip ZIP archive "
                                        + rel_file
                                        + ". Already scanned."
                                    )
                                else:
                                    logger.info(
                                        "DISPATCH discover_zip_entries zip=%s", file
                                    )
                                    all_futures.add(
                                        executor.submit(
                                            discover_zip_entries,
                                            file,
                                            book_extensions,
                                        )
                                    )
                            else:
                                rel_path = os.path.relpath(
                                    result.source_path, settings.SOPDS_ROOT_LIB
                                )
                                name = discovered_file.name
                                logger.info(
                                    "DISPATCH parse_standalone_book_job file=%s",
                                    file,
                                )
                                all_futures.add(
                                    executor.submit(
                                        parse_standalone_book_job,
                                        file,
                                        name,
                                        rel_path,
                                    )
                                )
                        continue

                    parse_result = result
                    if isinstance(parse_result, ContainerDiscovery):
                        logger.info(
                            "RESULT %s source=%s entries=%d err=%s",
                            (
                                "discover_inpx_entries"
                                if result.source_path
                                and result.source_path.lower().endswith(".inpx")
                                else "discover_zip_entries"
                            ),
                            result.source_path,
                            len(parse_result.entries),
                            parse_result.error,
                        )
                    else:
                        logger.info(
                            "RESULT parse worker books=%d bad=%d err=%s",
                            len(parse_result.books),
                            parse_result.bad_books,
                            parse_result.error,
                        )
                    if isinstance(parse_result, ContainerDiscovery):
                        result = parse_result
                        if result.error:
                            self.logger.error(
                                "Container discovery failed: " + result.error
                            )
                            self.bad_archives += 1
                            continue
                        if result.source_path is None:
                            self.logger.error(
                                "Container discovery missing source path; skipping"
                            )
                            self.bad_archives += 1
                            continue
                        is_inpx = (
                            result.source_path is not None
                            and result.source_path.lower().endswith(".inpx")
                        )
                        for entry in result.entries:
                            if is_inpx:
                                inpx_rel_path = os.path.relpath(
                                    result.source_path, settings.SOPDS_ROOT_LIB
                                )
                                legacy_inp_path = os.path.relpath(
                                    os.path.join(
                                        os.path.dirname(result.source_path), entry.name
                                    ),
                                    settings.SOPDS_ROOT_LIB,
                                )
                                opdsdb.normalize_inp_catalog(
                                    legacy_inp_path,
                                    os.path.join(inpx_rel_path, entry.name),
                                )
                                inp_path = os.path.join(inpx_rel_path, entry.name)
                                inp_cat = opdsdb.findcat(inp_path)
                                if (
                                    inp_cat is not None
                                    and inp_cat.cat_size != entry.size
                                ):
                                    inp_cat.cat_size = entry.size
                                    inp_cat.save(update_fields=["cat_size"])
                                logger.info(
                                    "DISPATCH parse_inp_job inpx=%s entry=%s",
                                    result.source_path,
                                    entry.name,
                                )
                                all_futures.add(
                                    executor.submit(
                                        parse_inp_job,
                                        result.source_path,
                                        entry.name,
                                        settings.SOPDS_ROOT_LIB,
                                        result.inpx_format,
                                        result.inpx_folders,
                                        config.SOPDS_INPX_TEST_ZIP,
                                        config.SOPDS_INPX_TEST_FILES,
                                    )
                                )
                            else:
                                rel_file = os.path.relpath(
                                    result.source_path, settings.SOPDS_ROOT_LIB
                                )
                                logger.info(
                                    "DISPATCH parse_zip_member_job zip=%s entry=%s",
                                    result.source_path,
                                    entry.name,
                                )
                                all_futures.add(
                                    executor.submit(
                                        parse_zip_member_job,
                                        result.source_path,
                                        entry.name,
                                        rel_file,
                                    )
                                )
                        if is_inpx:
                            inpx_rel_file = os.path.relpath(
                                result.source_path, settings.SOPDS_ROOT_LIB
                            )
                            inpx_cat = opdsdb.findcat(inpx_rel_file)
                            if inpx_cat is not None:
                                inpx_file_size = os.path.getsize(result.source_path)
                                if inpx_cat.cat_size != inpx_file_size:
                                    inpx_cat.cat_size = inpx_file_size
                                    inpx_cat.save(update_fields=["cat_size"])
                    else:
                        store_result(parse_result, self)

        if config.SOPDS_DELETE_LOGICAL:
            self.books_deleted = opdsdb.books_del_logical()
        else:
            self.books_deleted = opdsdb.books_del_phisical()
        self.catalogs_deleted = opdsdb.catalogs_del_empty()

        self.log_stats()

    def processzip(self, name: str, full_path: str, file: str) -> None:
        rel_file = os.path.relpath(file, settings.SOPDS_ROOT_LIB)
        zsize = os.path.getsize(file)
        if opdsdb.arc_skip(rel_file, zsize):
            self.arch_skipped += 1
            self.logger.debug("Skip ZIP archive " + rel_file + ". Already scanned.")
        else:
            zip_process_error = 0
            try:
                with zipfile.ZipFile(file, "r", allowZip64=True) as z:
                    filelist = z.namelist()
                    cat = opdsdb.addcattree(rel_file, opdsdb.CAT_ZIP, zsize)
                    for n in filelist:
                        try:
                            self.logger.debug(
                                "Start process ZIP file = " + file + " book file = " + n
                            )
                            file_size = z.getinfo(n).file_size
                            with z.open(n) as bookfile:
                                self.processfile(
                                    n,
                                    file,
                                    bookfile,
                                    cat,
                                    opdsdb.CAT_ZIP,
                                    file_size,
                                )
                        except zipfile.BadZipFile:
                            self.logger.warning(
                                "Error processing ZIP file = "
                                + file
                                + " book file = "
                                + n
                            )
                            zip_process_error = 1
                self.arch_scanned += 1
            except zipfile.BadZipFile:
                self.logger.warning(
                    "Error while read ZIP archive. File " + file + " corrupt."
                )
                zip_process_error = 1
            self.bad_archives += zip_process_error

    def processfile(
        self,
        name: str,
        full_path: str,
        file: Any,
        cat: Any,
        archive: int = 0,
        file_size: int = 0,
    ) -> None:
        n, e = os.path.splitext(name)
        if e.lower() in config.SOPDS_BOOK_EXTENSIONS.split():
            rel_path = os.path.relpath(full_path, settings.SOPDS_ROOT_LIB)
            self.logger.debug("Attempt to add book " + rel_path + "/" + name)
            try:
                if opdsdb.findbook(name, rel_path, 1) is None:
                    if archive == 0:
                        cat = opdsdb.addcattree(rel_path, archive)

                    try:
                        book_data = create_bookfile(file, name)
                    except Exception as err:
                        book_data = None
                        self.logger.warning(
                            rel_path
                            + " - "
                            + name
                            + " Book parse error, skipping... (Error: %s)" % err
                        )
                        self.bad_books += 1

                    if book_data:
                        lang = (
                            book_data.language_code.strip(strip_symbols)
                            if book_data.language_code
                            else ""
                        )
                        title = (
                            book_data.title.strip(strip_symbols)
                            if book_data.title
                            else n
                        )
                        annotation = (
                            book_data.description if book_data.description else ""
                        )
                        annotation = (
                            annotation.strip(strip_symbols)
                            if isinstance(annotation, str)
                            else annotation.decode("utf8").strip(strip_symbols)
                        )
                        docdate = book_data.docdate if book_data.docdate else ""

                        book = opdsdb.addbook(
                            name,
                            rel_path,
                            cat,
                            e[1:],
                            title,
                            annotation,
                            docdate,
                            lang,
                            file_size,
                            archive,
                        )
                        self.books_added += 1

                        if archive != 0:
                            self.books_in_archives += 1
                        self.logger.debug(
                            "Book " + rel_path + "/" + name + " Added ok."
                        )

                        for a in book_data.authors:
                            author_name = a.get("name", _("Unknown author")).strip(
                                strip_symbols
                            )
                            # Если в имени автора нет запятой, то фамилию
                            # переносим из конца в начало
                            if author_name and author_name.find(",") < 0:
                                author_names = author_name.split()
                                author_name = " ".join(
                                    [author_names[-1], " ".join(author_names[:-1])]
                                )
                            author = opdsdb.addauthor(author_name)
                            opdsdb.addbauthor(book, author)

                        for genre in book_data.tags:
                            opdsdb.addbgenre(
                                book,
                                opdsdb.addgenre(genre.lower().strip(strip_symbols)),
                            )

                        if book_data.series_info:
                            ser = opdsdb.addseries(book_data.series_info["title"])
                            ser_no = book_data.series_info["index"] or "0"
                            ser_no = int(ser_no) if ser_no.isdigit() else 0
                            opdsdb.addbseries(book, ser, ser_no)
                else:
                    self.books_skipped += 1
                    self.logger.debug(
                        "Book " + rel_path + "/" + name + " Already in DB."
                    )
            except UnicodeEncodeError as err:
                self.logger.warning(
                    rel_path
                    + " - "
                    + name
                    + " Book UnicodeEncodeError error, skipping... (Error: %s)" % err
                )
                self.bad_books += 1
