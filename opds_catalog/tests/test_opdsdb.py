from typing import cast

from django.test import TestCase

from opds_catalog import opdsdb
from opds_catalog.models import Book, Catalog, bseries


class opdsdbTestCase(TestCase):

    def setUp(self) -> None:
        opdsdb.clear_all()
        opdsdb.addcattree("root/child/subchild", opdsdb.CAT_NORMAL)
        book = opdsdb.addbook(
            "testbook.fb2",
            "root/child",
            cast(Catalog, opdsdb.findcat("root/child")),
            ".fb2",
            "Test Book",
            "Annotation",
            "01.01.2016",
            "ru",
            500,
            0,
        )
        opdsdb.addbauthor(book, opdsdb.addauthor("Test Author"))
        opdsdb.addbgenre(book, opdsdb.addgenre("fantastic"))
        opdsdb.addbseries(book, opdsdb.addseries("mywork"), 1)

    def test_cat_fn(self) -> None:
        """Тестирование функций addcattree, findcat"""
        self.assertEqual(Catalog.objects.filter(parent=None).count(), 1)
        self.assertEqual(Catalog.objects.all().count(), 4)

        cat = Catalog.objects.get(parent=None)
        self.assertEqual(cat.cat_name, ".")
        cat = Catalog.objects.get(parent=cat)
        self.assertEqual(cat.cat_name, "root")
        cat = Catalog.objects.get(parent=cat)
        self.assertEqual(cat.cat_name, "child")
        cat = Catalog.objects.get(parent=cat)
        self.assertEqual(cat.cat_name, "subchild")

        cat = cast(Catalog, opdsdb.findcat("root/child"))
        self.assertEqual(cat.cat_name, "child")
        self.assertEqual(cat.path, "root/child")
        parent = cast(Catalog, cat.parent)
        self.assertEqual(parent.cat_name, "root")
        grandparent = cast(Catalog, parent.parent)
        self.assertEqual(grandparent.cat_name, ".")
        self.assertIsNone(grandparent.parent)

    def test_book_fn(self) -> None:
        """Тестирование функций addbook, findbook"""
        book = cast(Book, opdsdb.findbook("testbook.fb2", "root/child"))
        self.assertIsNotNone(book)
        self.assertEqual(book.filename, "testbook.fb2")
        self.assertEqual(book.path, "root/child")
        self.assertEqual(book.catalog.cat_name, "child")
        self.assertEqual(book.catalog.cat_type, 0)
        self.assertEqual(book.format, ".fb2")
        self.assertEqual(book.title, "Test Book")
        self.assertEqual(book.annotation, "Annotation")
        self.assertEqual(book.docdate, "01.01.2016")
        self.assertEqual(book.lang, "ru")
        self.assertEqual(book.filesize, 500)
        self.assertEqual(book.cat_type, 0)

    def test_author_fn(self) -> None:
        """Тестирование функций addauthor, addbauthor"""
        book = cast(Book, opdsdb.findbook("testbook.fb2", "root/child"))
        self.assertEqual(book.authors.count(), 1)
        self.assertEqual(
            book.authors.get(full_name="Test Author").search_full_name, "TEST AUTHOR"
        )

    def test_genre_fn(self) -> None:
        """Тестирование функций addgenre, addbgenre"""
        book = cast(Book, opdsdb.findbook("testbook.fb2", "root/child"))
        self.assertEqual(book.genres.count(), 1)
        self.assertEqual(
            book.genres.get(genre="fantastic").section, opdsdb.unknown_genre
        )
        self.assertEqual(book.genres.get(genre="fantastic").subsection, "fantastic")

    def test_series_fn(self) -> None:
        """Тестирование функций addseries, addbseries"""
        book = cast(Book, opdsdb.findbook("testbook.fb2", "root/child"))
        self.assertEqual(book.series.count(), 1)
        ser = book.series.all()[0]
        self.assertEqual(ser.ser, "mywork")
        self.assertEqual(bseries.objects.get(ser=ser).ser_no, 1)

    def test_findbook_setavail_narrow_update(self) -> None:
        """setavail=1 must set avail=2 without touching other fields."""
        book = cast(Book, opdsdb.findbook("testbook.fb2", "root/child"))
        self.assertEqual(book.avail, 2)
        self.assertEqual(book.title, "Test Book")
        # Re-fetch to ensure other fields are preserved through the narrow UPDATE.
        same = cast(Book, opdsdb.findbook("testbook.fb2", "root/child", setavail=1))
        self.assertEqual(same.avail, 2)
        self.assertEqual(same.title, "Test Book")
        self.assertEqual(same.format, ".fb2")
        self.assertEqual(same.filesize, 500)

    def test_addcattree_no_duplicates(self) -> None:
        """Repeated addcattree on the same path must not create duplicates."""
        opdsdb.clear_cat_cache()
        opdsdb.addcattree("a/b/c", opdsdb.CAT_NORMAL)
        opdsdb.addcattree("a/b/c", opdsdb.CAT_NORMAL)
        self.assertEqual(Catalog.objects.filter(path="a/b/c").count(), 1)

    def test_catalogs_del_empty_removes_missing_branches(self) -> None:
        gone = opdsdb.addcattree("gone/nested", opdsdb.CAT_NORMAL)
        missing_book = opdsdb.addbook(
            "missing.fb2",
            "gone/nested",
            gone,
            "fb2",
            "Missing Book",
            "",
            "",
            "ru",
        )
        missing_book.delete()

        deleted = opdsdb.catalogs_del_empty()

        self.assertGreaterEqual(deleted, 2)
        self.assertFalse(Catalog.objects.filter(path="gone").exists())
        self.assertFalse(Book.objects.filter(pk=missing_book.pk).exists())
        self.assertTrue(Catalog.objects.filter(path="root/child").exists())
        self.assertTrue(Catalog.objects.filter(parent=None, path=".").exists())

    def test_catalogs_del_empty_preserves_logically_deleted_books(self) -> None:
        gone = opdsdb.addcattree("gone/nested", opdsdb.CAT_NORMAL)
        missing_book = opdsdb.addbook(
            "missing.fb2",
            "gone/nested",
            gone,
            "fb2",
            "Missing Book",
            "",
            "",
            "ru",
        )
        Book.objects.filter(pk=missing_book.pk).update(avail=0)

        opdsdb.catalogs_del_empty()

        self.assertTrue(Catalog.objects.filter(path="gone/nested").exists())
        self.assertTrue(Book.objects.filter(pk=missing_book.pk, avail=0).exists())

    def test_normalize_inp_catalog_reparents_catalog_and_books(self) -> None:
        opdsdb.addcattree("books/index.inpx", opdsdb.CAT_INPX)
        legacy = opdsdb.addcattree("books/part.inp", opdsdb.CAT_INP)
        book = opdsdb.addbook(
            "book.fb2",
            "books/part.inp",
            legacy,
            "fb2",
            "Book",
            "",
            "",
            "ru",
            archive=opdsdb.CAT_INP,
        )
        book_id = book.pk

        moved = opdsdb.normalize_inp_catalog(
            "books/part.inp",
            "books/index.inpx/part.inp",
        )

        book.refresh_from_db()
        legacy.refresh_from_db()
        self.assertEqual(moved, 1)
        self.assertEqual(book.pk, book_id)
        self.assertEqual(book.path, "books/index.inpx/part.inp")
        self.assertEqual(book.catalog, legacy)
        self.assertEqual(legacy.path, "books/index.inpx/part.inp")
        self.assertEqual(cast(Catalog, legacy.parent).path, "books/index.inpx")

        self.assertEqual(
            opdsdb.normalize_inp_catalog(
                "books/part.inp",
                "books/index.inpx/part.inp",
            ),
            0,
        )
