from __future__ import annotations

import logging
import os
import tempfile
from concurrent.futures import Future
from types import TracebackType
from typing import Any
from unittest import mock
from unittest.mock import patch

import django
from constance import config
from django.conf import settings as django_settings
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings

from opds_catalog import opdsdb

# from opds_catalog import settings
from opds_catalog.management.commands.sopds_scanner import Command
from opds_catalog.models import Author, Book, Catalog, Genre, Series
from opds_catalog.sopdscan import opdsScanner


class ImmediateExecutor:
    """Executor test double that completes submitted work synchronously."""

    def __init__(self) -> None:
        self.submitted: list[str] = []

    def __enter__(self) -> ImmediateExecutor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def submit(self, function: Any, *args: Any, **kwargs: Any) -> Future[Any]:
        self.submitted.append(function.__name__)
        future: Future[Any] = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future


class scanTestCase(TestCase):
    test_module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_ROOTLIB = os.path.join(test_module_path, "tests/data")
    test_fb2 = "262001.fb2"
    test_epub = "mirer.epub"
    test_mobi = "robin_cook.mobi"
    test_zip = "books.zip"

    def setUp(self) -> None:
        django_settings.SOPDS_ROOT_LIB = self.test_ROOTLIB

    def test_processfile_fb2(self) -> None:
        """Тестирование процедуры processfile (извлекает метаданные из книги \
FB2 и помещает в БД)"""
        opdsdb.clear_all()
        scanner = opdsScanner()
        scanner.processfile(
            self.test_fb2,
            self.test_ROOTLIB,
            os.path.join(self.test_ROOTLIB, self.test_fb2),
            None,
            0,
            495373,
        )
        book = Book.objects.get(filename=self.test_fb2)
        self.assertIsNotNone(book)
        self.assertEqual(scanner.books_added, 1)
        self.assertEqual(book.filename, self.test_fb2)
        self.assertEqual(book.path, ".")
        self.assertEqual(book.format, "fb2")
        self.assertEqual(book.cat_type, 0)
        # self.assertGreaterEqual(book.registerdate, )
        self.assertEqual(book.docdate, "30.1.2011")
        self.assertEqual(book.lang, "en")
        self.assertEqual(book.title, "The Sanctuary Sparrow")
        self.assertEqual(book.search_title, "The Sanctuary Sparrow".upper())
        self.assertEqual(book.annotation, "")
        self.assertEqual(book.avail, 2)
        self.assertEqual(book.catalog.path, ".")
        self.assertEqual(book.catalog.cat_name, ".")
        self.assertEqual(book.catalog.cat_type, 0)
        self.assertEqual(book.filesize, 495373)

        self.assertEqual(book.authors.count(), 1)
        self.assertEqual(
            book.authors.get(full_name="Peters Ellis").search_full_name, "PETERS ELLIS"
        )

        self.assertEqual(book.genres.count(), 1)
        self.assertEqual(book.genres.get(genre="antique").section, opdsdb.unknown_genre)
        self.assertEqual(book.genres.get(genre="antique").subsection, "antique")

    def test_processfile_fb2sax(self) -> None:
        config.SOPDS_FB2SAX = True
        self.test_processfile_fb2()

    def test_processfile_fb2xpath(self) -> None:
        config.SOPDS_FB2SAX = False
        self.test_processfile_fb2()

    def test_processfile_epub(self) -> None:
        """Тестирование процедуры processfile (извлекает метаданные из книги \
EPUB и помещает в БД)"""
        opdsdb.clear_all()
        scanner = opdsScanner()
        scanner.processfile(
            self.test_epub,
            self.test_ROOTLIB,
            os.path.join(self.test_ROOTLIB, self.test_epub),
            None,
            0,
            491279,
        )
        book = Book.objects.get(filename=self.test_epub)
        self.assertIsNotNone(book)
        self.assertEqual(scanner.books_added, 1)
        self.assertEqual(book.filename, self.test_epub)
        self.assertEqual(book.path, ".")
        self.assertEqual(book.format, "epub")
        self.assertEqual(book.cat_type, 0)
        # self.assertGreaterEqual(book.registerdate, )
        self.assertEqual(book.docdate, "2015")
        self.assertEqual(book.lang, "ru")
        self.assertEqual(book.title, "У меня девять жизней (шф (продолжатели))")
        self.assertEqual(
            book.search_title, "У меня девять жизней (шф (продолжатели))".upper()
        )
        self.assertEqual(book.annotation, "Собрание произведений. Том 2")
        self.assertEqual(book.avail, 2)
        self.assertEqual(book.catalog.path, ".")
        self.assertEqual(book.catalog.cat_name, ".")
        self.assertEqual(book.catalog.cat_type, 0)
        self.assertEqual(book.filesize, 491279)

        self.assertEqual(book.authors.count(), 1)
        self.assertEqual(
            book.authors.get(full_name="Мирер Александр").search_full_name,
            "МИРЕР АЛЕКСАНДР",
        )

        self.assertEqual(book.genres.count(), 1)
        self.assertEqual(book.genres.get(genre="sf").section, opdsdb.unknown_genre)
        self.assertEqual(book.genres.get(genre="sf").subsection, "sf")

    def test_processfile_mobi(self) -> None:
        """Тестирование процедуры processfile (извлекает метаданные из книги \
EPUB и помещает в БД)"""
        opdsdb.clear_all()
        scanner = opdsScanner()
        scanner.processfile(
            self.test_mobi,
            self.test_ROOTLIB,
            os.path.join(self.test_ROOTLIB, self.test_mobi),
            None,
            0,
            542811,
        )
        book = Book.objects.get(filename=self.test_mobi)
        self.assertIsNotNone(book)
        self.assertEqual(scanner.books_added, 1)
        self.assertEqual(book.filename, self.test_mobi)
        self.assertEqual(book.path, ".")
        self.assertEqual(book.format, "mobi")
        self.assertEqual(book.cat_type, 0)
        # self.assertGreaterEqual(book.registerdate, )
        self.assertEqual(book.docdate, "2011-11-20")
        self.assertEqual(book.lang, "")
        self.assertEqual(book.title, "Vector")
        self.assertEqual(book.search_title, "Vector".upper())
        self.assertEqual(book.annotation, "")
        self.assertEqual(book.avail, 2)
        self.assertEqual(book.catalog.path, ".")
        self.assertEqual(book.catalog.cat_name, ".")
        self.assertEqual(book.catalog.cat_type, 0)
        self.assertEqual(book.filesize, 542811)

        self.assertEqual(book.authors.count(), 1)
        self.assertEqual(
            book.authors.get(full_name="Cook Robin").search_full_name, "COOK ROBIN"
        )

    def test_discover_zip_entries_lists_members(self) -> None:
        """discover_zip_entries lists every member with name and size."""
        import tempfile

        from opds_catalog import zipf as zipfile
        from opds_catalog.scan_parser import discover_zip_entries

        members = {
            self.test_fb2: os.path.join(self.test_ROOTLIB, self.test_fb2),
            self.test_epub: os.path.join(self.test_ROOTLIB, self.test_epub),
        }
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = os.path.join(tmp, "discover.zip")
            with zipfile.ZipFile(archive_path, "w") as zf:
                for name, src in members.items():
                    with open(src, "rb") as fh:
                        zf.writestr(name, fh.read())

            discovery = discover_zip_entries(archive_path, (".fb2", ".epub"))

        self.assertIsNone(discovery.error)
        names = {e.name for e in discovery.entries}
        self.assertEqual(names, {self.test_fb2, self.test_epub})
        by_name = {e.name: e.size for e in discovery.entries}
        self.assertGreater(by_name[self.test_fb2], 0)
        self.assertGreater(by_name[self.test_epub], 0)

    def test_discover_zip_entries_ignores_non_books(self) -> None:
        """ZIP discovery must not dispatch INP indexes to the book parser."""
        import tempfile

        from opds_catalog import zipf as zipfile
        from opds_catalog.scan_parser import discover_zip_entries

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = os.path.join(tmp, "discover.zip")
            with zipfile.ZipFile(archive_path, "w") as zf:
                zf.writestr("index.inp", b"metadata")
                zf.writestr("notes.txt", b"notes")
                zf.writestr("book.fb2", b"book")

            discovery = discover_zip_entries(archive_path, (".fb2",))

        self.assertEqual([entry.name for entry in discovery.entries], ["book.fb2"])

    def test_parse_zip_member_job_parses_single_member(self) -> None:
        """parse_zip_member_job parses exactly one member of a ZIP archive."""
        import tempfile

        from opds_catalog import zipf as zipfile
        from opds_catalog.scan_parser import parse_zip_member_job

        src = os.path.join(self.test_ROOTLIB, self.test_fb2)
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = os.path.join(tmp, "member.zip")
            with zipfile.ZipFile(archive_path, "w") as zf:
                with open(src, "rb") as fh:
                    zf.writestr(self.test_fb2, fh.read())

            result = parse_zip_member_job(archive_path, self.test_fb2, ".")

        self.assertIsNone(result.error)
        self.assertEqual(result.bad_books, 0)
        self.assertEqual(len(result.books), 1)
        book = result.books[0]
        self.assertEqual(book.filename, self.test_fb2)
        self.assertEqual(book.title, "The Sanctuary Sparrow")
        self.assertEqual(book.cat_type, 1)

    def test_scanall(self) -> None:
        """Тестирование процедуры scanall (извлекает метаданные из книг и \
помещает в БД)"""
        opdsdb.clear_all()
        scanner = opdsScanner()
        executor = ImmediateExecutor()
        with patch(
            "opds_catalog.sopdscan.create_scan_executor",
            return_value=executor,
        ):
            scanner.scan_all()
        self.assertIn("discover_directory", executor.submitted)
        self.assertIn("discover_zip_entries", executor.submitted)
        self.assertIn("parse_zip_member_job", executor.submitted)
        self.assertIn("parse_standalone_book_job", executor.submitted)
        self.assertEqual(scanner.books_added, 6)
        self.assertEqual(scanner.bad_books, 1)
        self.assertEqual(Book.objects.all().count(), 6)
        self.assertEqual(Author.objects.all().count(), 6)
        self.assertEqual(Genre.objects.all().count(), 5)
        self.assertEqual(Series.objects.all().count(), 1)
        self.assertEqual(Catalog.objects.all().count(), 2)

    def test_clear_scan_caches(self) -> None:
        """Verify clear_scan_caches resets memo caches."""
        from opds_catalog.sopdscan import (
            _author_cache,
            _genre_cache,
            _series_cache,
            clear_scan_caches,
        )

        # Populate caches with dummy entries
        _author_cache["test"] = Author(full_name="test")
        _genre_cache["test"] = Genre(genre="test")
        _series_cache["test"] = Series(ser="test")
        self.assertEqual(len(_author_cache), 1)
        self.assertEqual(len(_genre_cache), 1)
        self.assertEqual(len(_series_cache), 1)

        clear_scan_caches()

        self.assertEqual(len(_author_cache), 0)
        self.assertEqual(len(_genre_cache), 0)
        self.assertEqual(len(_series_cache), 0)

    def test_store_result_adds_book(self) -> None:
        """Verify store_result writes a BookMeta to the database."""
        from opds_catalog.scan_types import AuthorMeta, BookMeta, ParseResult
        from opds_catalog.sopdscan import store_result

        opdsdb.clear_all()
        scanner = opdsScanner()
        meta = BookMeta(
            filename="test.fb2",
            rel_path=".",
            ext="fb2",
            title="Test Book",
            annotation="",
            docdate="2024",
            lang="en",
            filesize=100,
            cat_type=0,
            authors=[AuthorMeta(name="Doe John")],
            genres=["fiction"],
            series=[],
        )
        result = ParseResult(books=[meta])
        store_result(result, scanner)

        self.assertEqual(scanner.books_added, 1)
        self.assertEqual(scanner.books_skipped, 0)
        self.assertEqual(Book.objects.count(), 1)
        book = Book.objects.get(filename="test.fb2")
        self.assertEqual(book.title, "Test Book")
        self.assertEqual(book.authors.count(), 1)
        # first() returns Optional; safe here because count() == 1 above.
        author = book.authors.first()
        self.assertEqual(author.full_name, "Doe John")  # type: ignore[union-attr]
        self.assertEqual(book.genres.count(), 1)

    def test_store_result_skips_existing_book(self) -> None:
        """Verify store_result skips books already in the database."""
        from opds_catalog.scan_types import BookMeta, ParseResult
        from opds_catalog.sopdscan import store_result

        opdsdb.clear_all()
        scanner = opdsScanner()
        # Create a book first
        cat = opdsdb.addcattree(".", 0)
        opdsdb.addbook("test.fb2", ".", cat, "fb2", "Test", "", "2024", "en", 100, 0)

        meta = BookMeta(
            filename="test.fb2",
            rel_path=".",
            ext="fb2",
            title="Test Book",
            annotation="",
            docdate="2024",
            lang="en",
            filesize=100,
            cat_type=0,
        )
        result = ParseResult(books=[meta])
        store_result(result, scanner)

        self.assertEqual(scanner.books_added, 0)
        self.assertEqual(scanner.books_skipped, 1)
        self.assertEqual(Book.objects.count(), 1)

    def test_store_result_moves_inp_book_to_zip_without_recreating_it(self) -> None:
        """An INP result moves the existing book into its external ZIP."""
        from opds_catalog.scan_types import BookMeta, ParseResult
        from opds_catalog.sopdscan import store_result

        opdsdb.clear_all()
        scanner = opdsScanner()
        inp_path = "books/index.inpx/part.inp"
        inp_catalog = opdsdb.addcattree(inp_path, opdsdb.CAT_INP)
        book = opdsdb.addbook(
            "test.fb2",
            inp_path,
            inp_catalog,
            "fb2",
            "Test",
            "",
            "2024",
            "ru",
            100,
            opdsdb.CAT_INP,
        )
        book_id = book.pk
        zip_path = f"{inp_path}/part.zip"
        meta = BookMeta(
            filename="test.fb2",
            rel_path=zip_path,
            ext="fb2",
            title="Test",
            annotation="",
            docdate="2024",
            lang="ru",
            filesize=100,
            cat_type=opdsdb.CAT_INP,
            inp_rel_path=inp_path,
            legacy_inp_rel_path="books/part.inp",
        )

        store_result(ParseResult(books=[meta]), scanner)

        book.refresh_from_db()
        self.assertEqual(Book.objects.count(), 1)
        self.assertEqual(book.pk, book_id)
        self.assertEqual(book.path, zip_path)
        self.assertEqual(book.catalog.path, zip_path)
        self.assertEqual(scanner.books_skipped, 1)

    def test_store_result_propagates_bad_books(self) -> None:
        """Verify store_result adds bad_books count to scanner stats."""
        from opds_catalog.scan_types import ParseResult
        from opds_catalog.sopdscan import store_result

        opdsdb.clear_all()
        scanner = opdsScanner()
        result = ParseResult(bad_books=3)
        store_result(result, scanner)
        self.assertEqual(scanner.bad_books, 3)

    def test_store_result_counts_archived_books(self) -> None:
        """Verify store_result increments books_in_archives for non-zero cat_type."""
        from opds_catalog.scan_types import BookMeta, ParseResult
        from opds_catalog.sopdscan import store_result

        opdsdb.clear_all()
        scanner = opdsScanner()
        meta = BookMeta(
            filename="archived.fb2",
            rel_path="archive.zip",
            ext="fb2",
            title="Archived Book",
            annotation="",
            docdate="2024",
            lang="en",
            filesize=200,
            cat_type=1,
        )
        result = ParseResult(books=[meta])
        store_result(result, scanner)
        self.assertEqual(scanner.books_added, 1)
        self.assertEqual(scanner.books_in_archives, 1)

    def test_store_result_bulk_creates_shared_relations(self) -> None:
        """A result batch creates books and shared M2M rows without duplicates."""
        from opds_catalog.scan_types import (
            AuthorMeta,
            BookMeta,
            ParseResult,
            SeriesMeta,
        )
        from opds_catalog.sopdscan import store_result

        opdsdb.clear_all()
        scanner = opdsScanner()
        books = [
            BookMeta(
                filename=f"book-{index}.fb2",
                rel_path=".",
                ext="fb2",
                title=f"Book {index}",
                annotation="",
                docdate="2024",
                lang="en",
                filesize=100 + index,
                cat_type=0,
                authors=[AuthorMeta(name="Doe John")],
                genres=["fiction"],
                series=[SeriesMeta(title="Shared", index=index)],
            )
            for index in range(2)
        ]

        store_result(ParseResult(books=books), scanner)

        self.assertEqual(Book.objects.count(), 2)
        self.assertEqual(Author.objects.count(), 1)
        self.assertEqual(Genre.objects.count(), 1)
        self.assertEqual(Series.objects.count(), 1)
        self.assertEqual(sum(book.authors.count() for book in Book.objects.all()), 2)
        self.assertEqual(sum(book.genres.count() for book in Book.objects.all()), 2)
        self.assertEqual(sum(book.series.count() for book in Book.objects.all()), 2)
        self.assertEqual(scanner.books_added, 2)

    def test_store_books_batch_uses_batch_size_when_configured(self) -> None:
        """All bulk_create calls receive batch_size when the setting is > 0."""
        from unittest.mock import patch

        from django.test import override_settings

        from opds_catalog import models as catalog_models
        from opds_catalog.scan_types import (
            AuthorMeta,
            BookMeta,
            SeriesMeta,
        )
        from opds_catalog.sopdscan import _store_books_batch, opdsScanner

        opdsdb.clear_all()
        scanner = opdsScanner()
        meta = BookMeta(
            filename="book.fb2",
            rel_path=".",
            ext="fb2",
            title="Book",
            annotation="",
            docdate="2024",
            lang="en",
            filesize=100,
            cat_type=0,
            authors=[AuthorMeta(name="Doe John")],
            genres=["fiction"],
            series=[SeriesMeta(title="Shared", index=1)],
        )

        expected = 100
        with override_settings(SOPDS_SCAN_DB_BATCH_SIZE=expected):
            with (
                patch.object(
                    catalog_models.Author.objects, "bulk_create"
                ) as author_bulk,
                patch.object(catalog_models.Genre.objects, "bulk_create") as genre_bulk,
                patch.object(
                    catalog_models.Series.objects, "bulk_create"
                ) as series_bulk,
                patch.object(catalog_models.Book.objects, "bulk_create") as book_bulk,
                patch.object(
                    catalog_models.bauthor.objects, "bulk_create"
                ) as bauthor_bulk,
                patch.object(
                    catalog_models.bgenre.objects, "bulk_create"
                ) as bgenre_bulk,
                patch.object(
                    catalog_models.bseries.objects, "bulk_create"
                ) as bseries_bulk,
            ):
                _store_books_batch([meta], scanner)

        for bulk in (
            author_bulk,
            genre_bulk,
            series_bulk,
            book_bulk,
            bauthor_bulk,
            bgenre_bulk,
            bseries_bulk,
        ):
            bulk.assert_called_once()
            self.assertEqual(bulk.call_args.kwargs.get("batch_size"), expected)

    def test_store_books_batch_uses_none_batch_size_by_default(self) -> None:
        """With the default setting 0, batch_size is passed as None."""
        from unittest.mock import patch

        from opds_catalog import models as catalog_models
        from opds_catalog.scan_types import (
            AuthorMeta,
            BookMeta,
            SeriesMeta,
        )
        from opds_catalog.sopdscan import _store_books_batch, opdsScanner

        opdsdb.clear_all()
        scanner = opdsScanner()
        meta = BookMeta(
            filename="book.fb2",
            rel_path=".",
            ext="fb2",
            title="Book",
            annotation="",
            docdate="2024",
            lang="en",
            filesize=100,
            cat_type=0,
            authors=[AuthorMeta(name="Doe John")],
            genres=["fiction"],
            series=[SeriesMeta(title="Shared", index=1)],
        )

        with (
            patch.object(catalog_models.Author.objects, "bulk_create") as author_bulk,
            patch.object(catalog_models.Genre.objects, "bulk_create") as genre_bulk,
            patch.object(catalog_models.Series.objects, "bulk_create") as series_bulk,
            patch.object(catalog_models.Book.objects, "bulk_create") as book_bulk,
            patch.object(catalog_models.bauthor.objects, "bulk_create") as bauthor_bulk,
            patch.object(catalog_models.bgenre.objects, "bulk_create") as bgenre_bulk,
            patch.object(catalog_models.bseries.objects, "bulk_create") as bseries_bulk,
        ):
            _store_books_batch([meta], scanner)

        for bulk in (
            author_bulk,
            genre_bulk,
            series_bulk,
            book_bulk,
            bauthor_bulk,
            bgenre_bulk,
            bseries_bulk,
        ):
            bulk.assert_called_once()
            self.assertIsNone(bulk.call_args.kwargs.get("batch_size"))

    def test_store_result_skips_duplicate_inside_batch(self) -> None:
        """Duplicate file/path pairs in one worker result are inserted once."""
        from opds_catalog.scan_types import BookMeta, ParseResult
        from opds_catalog.sopdscan import store_result

        opdsdb.clear_all()
        scanner = opdsScanner()
        meta = BookMeta(
            filename="duplicate.fb2",
            rel_path=".",
            ext="fb2",
            title="Duplicate",
            annotation="",
            docdate="2024",
            lang="en",
            filesize=100,
            cat_type=0,
        )

        store_result(ParseResult(books=[meta, meta]), scanner)

        self.assertEqual(Book.objects.count(), 1)
        self.assertEqual(scanner.books_added, 1)
        self.assertEqual(scanner.books_skipped, 1)

    def test_parse_standalone_book_job(self) -> None:
        """Verify parse_standalone_book_job reads a file and returns ParseResult."""
        from opds_catalog.scan_parser import parse_standalone_book_job

        path = os.path.join(self.test_ROOTLIB, self.test_fb2)
        result = parse_standalone_book_job(path, self.test_fb2, ".")
        self.assertEqual(len(result.books), 1)
        self.assertEqual(result.books[0].filename, self.test_fb2)
        self.assertEqual(result.books[0].title, "The Sanctuary Sparrow")
        self.assertEqual(result.bad_books, 0)


class InpxCatalogSizeTestCase(TestCase):
    """Verify that scan_all preserves cat_size on INPX and INP catalogs."""

    INPX_FORMAT = "AUTHOR;GENRE;TITLE;SERIES;SERNO;FILE;SIZE;LIBID;DEL;EXT;DATE;LANG"
    INP_RECORD = (
        b"Author\x04Genre\x04Test Book\x04Series\x040"
        b"\x04book\x0412345\x04lib\x040\x04fb2\x042024\x04en"
    )

    def _make_inpx(self, tmp: str) -> str:
        """Create a minimal INPX archive with one .inp entry."""
        import zipfile as _zipfile

        inpx_path = os.path.join(tmp, "test.index.inpx")
        with _zipfile.ZipFile(inpx_path, "w") as zf:
            zf.writestr("structure.info", self.INPX_FORMAT)
            zf.writestr("test.inp", self.INP_RECORD)
        return inpx_path

    def test_inp_catalog_cat_size_matches_entry_size(self) -> None:
        """Patch 3: INP catalog must get cat_size from ContainerEntry.size."""
        import zipfile as _zipfile

        opdsdb.clear_all()
        config.SOPDS_INPX_ENABLE = True
        config.SOPDS_INPX_SKIP_UNCHANGED = False
        scanner = opdsScanner()
        executor = ImmediateExecutor()

        with tempfile.TemporaryDirectory() as tmp:
            inpx_path = self._make_inpx(tmp)
            with _zipfile.ZipFile(inpx_path, "r") as zf:
                inp_entry_size = zf.getinfo("test.inp").file_size

            # Pre-create the legacy INP catalog so normalize_inp_catalog
            # can reparent it under the INPX catalog. This simulates a
            # re-scan where the INP was already scanned previously.
            inp_legacy_path = os.path.relpath(
                os.path.join(os.path.dirname(inpx_path), "test.inp"),
                tmp,
            )
            # Also pre-create the INPX catalog so that normalize_inp_catalog
            # can set the right parent.
            inpx_rel = os.path.relpath(inpx_path, tmp)
            opdsdb.addcattree(
                inpx_rel, opdsdb.CAT_INPX, size=os.path.getsize(inpx_path)
            )
            legacy_inp = opdsdb.addcattree(inp_legacy_path, opdsdb.CAT_INP, size=0)
            self.assertEqual(legacy_inp.cat_size, 0)

            django_settings.SOPDS_ROOT_LIB = tmp

            with patch(
                "opds_catalog.sopdscan.create_scan_executor",
                return_value=executor,
            ):
                scanner.scan_all()

            inp_rel = os.path.join(inpx_rel, "test.inp")
            inp_cat = opdsdb.findcat(inp_rel)
            self.assertIsNotNone(inp_cat, f"INP catalog not found for {inp_rel}")
            cat_size = inp_cat.cat_size  # type: ignore[union-attr]
            self.assertEqual(cat_size, inp_entry_size)

    def test_inpx_catalog_cat_size_matches_filesystem(self) -> None:
        """Patch 4: INPX catalog must get cat_size from the actual file on disk,
        even if the catalog already exists with a stale size."""
        opdsdb.clear_all()
        config.SOPDS_INPX_ENABLE = True
        config.SOPDS_INPX_SKIP_UNCHANGED = False
        scanner = opdsScanner()
        executor = ImmediateExecutor()

        with tempfile.TemporaryDirectory() as tmp:
            inpx_path = self._make_inpx(tmp)
            inpx_file_size = os.path.getsize(inpx_path)

            # Pre-create the INPX catalog with a wrong cat_size to simulate
            # a stale entry from a previous scan.
            inpx_rel = os.path.relpath(inpx_path, tmp)
            stale_cat = opdsdb.addcattree(inpx_rel, opdsdb.CAT_INPX, size=0)
            self.assertEqual(stale_cat.cat_size, 0)

            django_settings.SOPDS_ROOT_LIB = tmp

            with patch(
                "opds_catalog.sopdscan.create_scan_executor",
                return_value=executor,
            ):
                scanner.scan_all()

            inpx_cat = opdsdb.findcat(inpx_rel)

            self.assertIsNotNone(inpx_cat, f"INPX catalog not found for {inpx_rel}")
            cat_size = inpx_cat.cat_size  # type: ignore[union-attr]
            self.assertEqual(cat_size, inpx_file_size)


class ZipCatalogSizeTestCase(TestCase):
    """Verify that scan_all preserves cat_size on ZIP catalogs."""

    def _make_zip(self, tmp: str) -> str:
        """Create a minimal ZIP archive with one .fb2 book."""
        from opds_catalog import zipf as zipfile

        src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tests/data/262001.fb2",
        )
        zip_path = os.path.join(tmp, "test_archive.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            with open(src, "rb") as fh:
                zf.writestr("262001.fb2", fh.read())
        return zip_path

    def test_zip_catalog_cat_size_matches_filesystem(self) -> None:
        """ZIP catalog must get cat_size from the actual file on disk,
        even if the catalog already exists with a stale size."""
        opdsdb.clear_all()
        config.SOPDS_ZIPSCAN = True
        config.SOPDS_INPX_ENABLE = True
        config.SOPDS_INPX_SKIP_UNCHANGED = False
        scanner = opdsScanner()
        executor = ImmediateExecutor()

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = self._make_zip(tmp)
            zip_file_size = os.path.getsize(zip_path)

            # Pre-create the ZIP catalog with a wrong cat_size to simulate
            # a stale entry from a previous scan.
            zip_rel = os.path.relpath(zip_path, tmp)
            stale_cat = opdsdb.addcattree(zip_rel, opdsdb.CAT_ZIP, size=0)
            self.assertEqual(stale_cat.cat_size, 0)

            django_settings.SOPDS_ROOT_LIB = tmp

            with patch(
                "opds_catalog.sopdscan.create_scan_executor",
                return_value=executor,
            ):
                scanner.scan_all()

            zip_cat = opdsdb.findcat(zip_rel)

            self.assertIsNotNone(zip_cat, f"ZIP catalog not found for {zip_rel}")
            cat_size = zip_cat.cat_size  # type: ignore[union-attr]
            self.assertEqual(cat_size, zip_file_size)

    def test_zip_unchanged_skip(self) -> None:
        """Second scan must skip ZIP when size unchanged and mark books avail=2."""
        opdsdb.clear_all()
        config.SOPDS_ZIPSCAN = True
        config.SOPDS_INPX_ENABLE = False
        config.SOPDS_ZIP_SKIP_UNCHANGED = True
        scanner = opdsScanner()
        executor = ImmediateExecutor()

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = self._make_zip(tmp)
            django_settings.SOPDS_ROOT_LIB = tmp

            # --- first scan: ZIP must be dispatched (not skipped) ---
            with patch(
                "opds_catalog.sopdscan.create_scan_executor",
                return_value=executor,
            ):
                scanner.scan_all()

            self.assertEqual(
                executor.submitted.count("discover_zip_entries"),
                1,
                "First scan must dispatch discover_zip_entries",
            )

            zip_rel = os.path.relpath(zip_path, tmp)
            zip_cat = opdsdb.findcat(zip_rel)
            self.assertIsNotNone(zip_cat)

            # Books inserted by the first scan should exist.
            books_after_first = Book.objects.filter(catalog=zip_cat).count()
            self.assertGreater(books_after_first, 0)

            # --- second scan: ZIP must be skipped ---
            executor.submitted.clear()
            scanner.arch_skipped = 0

            with patch(
                "opds_catalog.sopdscan.create_scan_executor",
                return_value=executor,
            ):
                scanner.scan_all()

            self.assertEqual(
                executor.submitted.count("discover_zip_entries"),
                0,
                "Second scan must NOT dispatch discover_zip_entries",
            )
            self.assertGreater(scanner.arch_skipped, 0)

            # All books from the ZIP must have avail=2.
            skipped_books = Book.objects.filter(catalog=zip_cat, avail=2).count()
            self.assertEqual(
                skipped_books,
                books_after_first,
                "All books must be marked avail=2 on skip",
            )


class ScanIsActiveResetTestCase(TestCase):
    """Verify that scan_is_active is always reset even when scan_all() raises."""

    def setUp(self) -> None:
        self.cmd = Command()
        self.cmd.logger = logging.getLogger("test_scanner")
        self.cmd.logger.setLevel(logging.DEBUG)

    def test_command_accepts_only_foreground_actions(self) -> None:
        """Process supervision owns daemon stop/restart lifecycle operations."""
        parser = self.cmd.create_parser("manage.py", "sopds_scanner")
        self.assertEqual(parser.parse_args(["scan"]).command, "scan")
        self.assertEqual(parser.parse_args(["start"]).command, "start")
        with self.assertRaises(CommandError):
            parser.parse_args(["stop"])

    @patch("opds_catalog.management.commands.sopds_scanner.opdsScanner")
    def test_scan_is_active_resets_on_exception(self, mock_scanner_cls: Any) -> None:
        """scan_is_active must be False after scan() returns, even on failure."""
        mock_instance = mock_scanner_cls.return_value
        mock_instance.scan_all.side_effect = RuntimeError("simulated failure")

        self.assertFalse(self.cmd.scan_is_active)
        self.cmd.scan()

        self.assertFalse(self.cmd.scan_is_active)

    @patch("opds_catalog.management.commands.sopds_scanner.opdsScanner")
    def test_scan_logs_exception_on_failure(self, mock_scanner_cls: Any) -> None:
        """Unhandled scan_all() exceptions must be logged."""
        mock_instance = mock_scanner_cls.return_value
        mock_instance.scan_all.side_effect = RuntimeError("simulated failure")

        with self.assertLogs("test_scanner", level=logging.ERROR) as cm:
            self.cmd.scan()

        self.assertTrue(
            any("simulated failure" in msg for msg in cm.output),
            "Expected error log containing 'simulated failure'",
        )

    @patch("opds_catalog.management.commands.sopds_scanner.opdsScanner")
    def test_scan_raises_when_suppress_errors_false(
        self, mock_scanner_cls: Any
    ) -> None:
        """scan(suppress_errors=False) must re-raise the exception."""
        mock_instance = mock_scanner_cls.return_value
        mock_instance.scan_all.side_effect = RuntimeError("simulated failure")

        with self.assertRaises(RuntimeError):
            self.cmd.scan(suppress_errors=False)

        self.assertFalse(self.cmd.scan_is_active)


class BulkRetryTestCase(TestCase):
    """Retry logic for bulk DB operations."""

    @override_settings(
        SOPDS_SCAN_DB_RETRY_COUNT=0,
        SOPDS_SCAN_DB_RETRY_DELAY=0,
    )
    def test_batch_no_retry_on_operational_error(self) -> None:
        """With retry_count=0, a connection error is raised immediately."""
        from opds_catalog.sopdscan import _store_books_batch

        scanner = opdsScanner()
        with (
            mock.patch(
                "opds_catalog.sopdscan._store_books_batch_atomic",
                side_effect=django.db.utils.OperationalError("gone away"),
            ) as atomic_batch,
            mock.patch("opds_catalog.sopdscan.connection.close") as close,
            mock.patch("opds_catalog.sopdscan.time.sleep") as sleep,
        ):
            with self.assertRaises(django.db.utils.OperationalError):
                _store_books_batch([mock.Mock()], scanner)
        atomic_batch.assert_called_once()
        close.assert_called_once()
        sleep.assert_not_called()

    @override_settings(
        SOPDS_SCAN_DB_RETRY_COUNT=2,
        SOPDS_SCAN_DB_RETRY_DELAY=100,
    )
    def test_batch_retries_connection_errors(self) -> None:
        """The complete atomic batch is retried with exponential backoff."""
        from opds_catalog.sopdscan import _store_books_batch

        scanner = opdsScanner()
        error = django.db.utils.OperationalError("gone away")
        with (
            mock.patch(
                "opds_catalog.sopdscan._store_books_batch_atomic",
                side_effect=[error, error, None],
            ) as atomic_batch,
            mock.patch("opds_catalog.sopdscan.connection.close") as close,
            mock.patch("opds_catalog.sopdscan.time.sleep") as sleep,
        ):
            _store_books_batch([mock.Mock()], scanner)
        self.assertEqual(atomic_batch.call_count, 3)
        self.assertEqual(close.call_count, 2)
        sleep.assert_has_calls([mock.call(0.1), mock.call(0.2)])

    @override_settings(
        SOPDS_SCAN_DB_RETRY_COUNT=2,
        SOPDS_SCAN_DB_RETRY_DELAY=100,
    )
    def test_batch_exhausts_retries(self) -> None:
        """The final connection error is raised after all attempts fail."""
        from opds_catalog.sopdscan import _store_books_batch

        scanner = opdsScanner()
        with (
            mock.patch(
                "opds_catalog.sopdscan._store_books_batch_atomic",
                side_effect=django.db.utils.OperationalError("gone away"),
            ) as atomic_batch,
            mock.patch("opds_catalog.sopdscan.connection.close"),
            mock.patch("opds_catalog.sopdscan.time.sleep") as sleep,
        ):
            with self.assertRaises(django.db.utils.OperationalError):
                _store_books_batch([mock.Mock()], scanner)
        self.assertEqual(atomic_batch.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @override_settings(
        SOPDS_SCAN_DB_RETRY_COUNT=1,
        SOPDS_SCAN_DB_RETRY_DELAY=0,
    )
    def test_batch_retry_rolls_back_the_complete_insert(self) -> None:
        """A post-insert disconnect retries without leaving partial rows."""
        from opds_catalog.scan_types import BookMeta
        from opds_catalog.sopdscan import _store_books_batch

        opdsdb.clear_all()
        scanner = opdsScanner()
        meta = BookMeta(
            filename="retry.fb2",
            rel_path=".",
            ext="fb2",
            title="Retry",
            annotation="",
            docdate="2024",
            lang="en",
            filesize=100,
            cat_type=0,
        )
        real_bulk_create = Book.objects.bulk_create
        calls = 0

        def disconnect_after_insert(*args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            result = real_bulk_create(*args, **kwargs)
            if calls == 1:
                raise django.db.utils.OperationalError(2006, "server has gone away")
            return result

        with (
            mock.patch.object(
                Book.objects, "bulk_create", side_effect=disconnect_after_insert
            ),
            mock.patch("opds_catalog.sopdscan.connection.close"),
            mock.patch("opds_catalog.sopdscan.time.sleep"),
        ):
            _store_books_batch([meta], scanner)

        self.assertEqual(calls, 2)
        self.assertEqual(Book.objects.filter(filename="retry.fb2").count(), 1)
        self.assertEqual(scanner.books_added, 1)

    def test_log_bulk_emits_info_message(self) -> None:
        """_log_bulk sends INFO message with correct parameters."""
        from opds_catalog.sopdscan import _log_bulk

        logger = logging.getLogger("test.log_bulk")
        with self.assertLogs("test.log_bulk", level="INFO") as cm:
            _log_bulk(logger, "Author", "create", 42, 100, 12.3)
        self.assertEqual(len(cm.output), 1)
        msg = cm.output[0]
        self.assertIn("Author", msg)
        self.assertIn("create", msg)
        self.assertIn("42", msg)
        self.assertIn("100", msg)
        self.assertIn("12.3", msg)

    def test_log_bulk_skips_zero_count(self) -> None:
        """_log_bulk does nothing when count is 0."""
        from opds_catalog.sopdscan import _log_bulk

        logger = logging.getLogger("test.log_bulk_zero")
        _log_bulk(logger, "Author", "create", 0, None, 0.0)

    def test_log_bulk_shows_auto_for_none_batch_size(self) -> None:
        """_log_bulk shows 'auto' when batch_size is None."""
        from opds_catalog.sopdscan import _log_bulk

        logger = logging.getLogger("test.log_bulk_auto")
        with self.assertLogs("test.log_bulk_auto", level="INFO") as cm:
            _log_bulk(logger, "Book", "update", 10, None, 5.0)
        self.assertEqual(len(cm.output), 1)
        self.assertIn("auto", cm.output[0])


class DatabaseDisconnectRetryTestCase(TransactionTestCase):
    """Retry a batch after the underlying database connection is lost."""

    @override_settings(
        SOPDS_SCAN_DB_RETRY_COUNT=1,
        SOPDS_SCAN_DB_RETRY_DELAY=0,
    )
    def test_store_batch_reconnects_after_real_disconnect(self) -> None:
        from opds_catalog.scan_types import BookMeta
        from opds_catalog.sopdscan import _store_books_batch

        scanner = opdsScanner()
        meta = BookMeta(
            filename="reconnect.fb2",
            rel_path=".",
            ext="fb2",
            title="Reconnect",
            annotation="",
            docdate="2024",
            lang="en",
            filesize=100,
            cat_type=0,
        )

        connection.ensure_connection()
        raw_connection = connection.connection
        self.assertIsNotNone(raw_connection)
        raw_connection.close()

        with mock.patch("opds_catalog.sopdscan.time.sleep") as sleep:
            _store_books_batch([meta], scanner)

        sleep.assert_called_once_with(0)
        self.assertEqual(Book.objects.filter(filename="reconnect.fb2").count(), 1)
        self.assertEqual(scanner.books_added, 1)
