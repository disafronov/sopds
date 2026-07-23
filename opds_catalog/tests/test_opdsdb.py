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
        self.assertEqual(book.catalog.path, "root/child")
        self.assertEqual(book.catalog.cat_name, "child")
        self.assertEqual(book.catalog.cat_type, 0)
        self.assertEqual(book.format, ".fb2")
        self.assertEqual(book.title, "Test Book")
        self.assertEqual(book.annotation, "Annotation")
        self.assertEqual(book.docdate, "01.01.2016")
        self.assertEqual(book.lang, "ru")
        self.assertEqual(book.filesize, 500)
        self.assertEqual(book.catalog.cat_type, 0)

    def test_author_fn(self) -> None:
        """Тестирование функций addauthor, addbauthor"""
        book = cast(Book, opdsdb.findbook("testbook.fb2", "root/child"))
        self.assertEqual(book.authors.count(), 1)
        self.assertEqual(
            book.authors.get(full_name="Test Author").full_name, "Test Author"
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

    def test_avail_check_abort_restores_unchecked_books(self) -> None:
        book = cast(Book, opdsdb.findbook("testbook.fb2", "root/child"))
        opdsdb.avail_check_prepare()
        book.refresh_from_db()
        self.assertEqual(book.avail, 1)

        restored = opdsdb.avail_check_abort()

        book.refresh_from_db()
        self.assertEqual(restored, 1)
        self.assertEqual(book.avail, 2)

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

    def test_catalogs_del_empty_removes_empty_container_catalogs(self) -> None:
        """catalogs_del_empty must delete empty leaf catalogs regardless of cat_type."""
        opdsdb.addcattree("arch/index.inpx", opdsdb.CAT_INPX, size=9999)
        opdsdb.addcattree("arch/inner.zip", opdsdb.CAT_ZIP, size=8888)
        opdsdb.addcattree("arch/index.inpx/part.inp", opdsdb.CAT_INP, size=7777)

        deleted = opdsdb.catalogs_del_empty()

        self.assertGreaterEqual(deleted, 3)
        self.assertFalse(Catalog.objects.filter(path="arch/inner.zip").exists())
        self.assertFalse(
            Catalog.objects.filter(path="arch/index.inpx/part.inp").exists()
        )

    def test_catalogs_del_empty_deletes_regular_empty_leaf(self) -> None:
        """catalogs_del_empty with an empty leaf regular node must still delete it."""
        opdsdb.addcattree("gone/nested/leaf", opdsdb.CAT_NORMAL)
        opdsdb.catalogs_del_empty()
        self.assertFalse(Catalog.objects.filter(path="gone/nested/leaf").exists())

    def test_addcattree_updates_cat_size_on_existing(self) -> None:
        """addcattree must update cat_size when size differs on an existing catalog."""
        cat = opdsdb.addcattree("sized/leaf", opdsdb.CAT_NORMAL, size=0)
        self.assertEqual(cat.cat_size, 0)

        updated = opdsdb.addcattree("sized/leaf", opdsdb.CAT_NORMAL, size=42)
        updated.refresh_from_db()
        self.assertEqual(updated.cat_size, 42)

    def test_addcattree_preserves_cat_size_when_same(self) -> None:
        """addcattree must not touch cat_size when the size is already correct."""
        cat = opdsdb.addcattree("same/leaf", opdsdb.CAT_NORMAL, size=100)
        self.assertEqual(cat.cat_size, 100)

        same = opdsdb.addcattree("same/leaf", opdsdb.CAT_NORMAL, size=100)
        same.refresh_from_db()
        self.assertEqual(same.cat_size, 100)


class ZipSkipTestCase(TestCase):
    """Tests for the zip_skip helper function."""

    def setUp(self) -> None:
        opdsdb.clear_all()

    def test_zip_skip_returns_zero_when_catalog_missing(self) -> None:
        """zip_skip must return 0 when no catalog exists for the path."""
        result = opdsdb.zip_skip("nonexistent/archive.zip", 12345)
        self.assertEqual(result, 0)

    def test_zip_skip_returns_zero_when_size_differs(self) -> None:
        """zip_skip must return 0 when the on-disk size differs from stored."""
        opdsdb.addcattree("books/archive.zip", opdsdb.CAT_ZIP, size=100)
        result = opdsdb.zip_skip("books/archive.zip", 9999)
        self.assertEqual(result, 0)

    def test_zip_skip_marks_books_avail2_on_match(self) -> None:
        """zip_skip must set avail=2 on all books and return their count."""
        zip_cat = opdsdb.addcattree("books/archive.zip", opdsdb.CAT_ZIP, size=500)
        book1 = opdsdb.addbook(
            "first.fb2",
            "books/archive.zip",
            zip_cat,
            ".fb2",
            "First",
            "",
            "",
            "ru",
        )
        book2 = opdsdb.addbook(
            "second.fb2",
            "books/archive.zip",
            zip_cat,
            ".fb2",
            "Second",
            "",
            "",
            "ru",
        )
        # Reset avail to 0 so we can verify zip_skip changes it.
        Book.objects.filter(pk__in=[book1.pk, book2.pk]).update(avail=0)
        book1.refresh_from_db()
        book2.refresh_from_db()
        self.assertEqual(book1.avail, 0)
        self.assertEqual(book2.avail, 0)

        result = opdsdb.zip_skip("books/archive.zip", 500)

        self.assertEqual(result, 2)
        book1.refresh_from_db()
        book2.refresh_from_db()
        self.assertEqual(book1.avail, 2)
        self.assertEqual(book2.avail, 2)
