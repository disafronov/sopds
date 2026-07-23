from datetime import datetime

from django.conf import settings as main_settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from opds_catalog import models, opdsdb
from opds_catalog.models import (
    Author,
    Book,
    Catalog,
    Counter,
    Genre,
    Series,
    bauthor,
    bgenre,
    bookshelf,
    bseries,
)


class modelsTestCase(TestCase):
    testdatetime = datetime(2016, 1, 1, 0, 0)
    if main_settings.USE_TZ:
        testdatetime = testdatetime.replace(tzinfo=timezone.get_current_timezone())

    def setUp(self) -> None:
        opdsdb.clear_all()
        book = Book.objects.create(
            filename="testbook.fb2",
            filesize=500,
            format="fb2",
            registerdate=self.testdatetime,
            docdate="01.01.2016",
            lang="ru",
            title="Книга",
            annotation="Аннотация",
            avail=2,
            catalog=Catalog.objects.create(
                parent=None, cat_name=".", path=".", cat_type=0
            ),
        )
        author = Author.objects.create(full_name="Шелепнев Дмитрий")
        genre = Genre.objects.create(
            genre="fantastic0", section="fantastic1", subsection="fantastic2"
        )
        series = Series.objects.create(ser="mywork")
        bauthor.objects.create(book=book, author=author)
        bgenre.objects.create(book=book, genre=genre)
        bseries.objects.create(book=book, ser=series, ser_no=1)
        user = User.objects.create_user(
            "testuser",
            "testuser@example.com",
            "testpassword",
            first_name="Test",
            last_name="User",
        )
        bookshelf.objects.create(user=user, book=book, readtime=self.testdatetime)
        Counter.objects.update_known_counters()

    def test_Book(self) -> None:
        """Тестирование соответствия структуры модели Book и работоспособности БД"""
        book = Book.objects.get(title="Книга")
        self.assertEqual(book.filename, "testbook.fb2")
        self.assertEqual(book.catalog.path, ".")
        self.assertEqual(book.filesize, 500)
        self.assertEqual(book.format, "fb2")
        self.assertEqual(book.catalog.cat_type, 0)
        self.assertEqual(book.registerdate, self.testdatetime)
        self.assertEqual(book.docdate, "01.01.2016")
        self.assertEqual(book.lang, "ru")
        self.assertEqual(book.title, "Книга")
        self.assertEqual(book.annotation, "Аннотация")
        self.assertEqual(book.avail, 2)
        self.assertEqual(book.catalog.path, ".")
        self.assertEqual(book.catalog.cat_name, ".")
        self.assertEqual(book.catalog.cat_type, 0)

    def test_Author(self) -> None:
        """Тестирование соответствия структуры моделей Author и bauthor и \
работоспособности БД"""
        book = Book.objects.get(title="Книга")
        self.assertEqual(book.authors.count(), 1)
        self.assertEqual(
            book.authors.get(full_name="Шелепнев Дмитрий").full_name,
            "Шелепнев Дмитрий",
        )

    def test_Genre(self) -> None:
        """Тестирование соответствия структуры моделей Genre и bgenre и \
работоспособности БД"""
        book = Book.objects.get(title="Книга")
        self.assertEqual(book.genres.count(), 1)
        self.assertEqual(book.genres.get(genre="fantastic0").section, "fantastic1")
        self.assertEqual(book.genres.get(genre="fantastic0").subsection, "fantastic2")

    def test_Series(self) -> None:
        """Тестирование соответствия структуры моделей Series и bseries и \
работоспособности БД"""
        book = Book.objects.get(title="Книга")
        self.assertEqual(book.series.count(), 1)
        ser = book.series.all()[0]
        self.assertEqual(ser.ser, "mywork")
        self.assertEqual(bseries.objects.get(ser=ser).ser_no, 1)

    def test_bookshelf(self) -> None:
        """Тестирование соответствия структуры модели bookshelf и \
работоспособности БД"""
        user = User.objects.get(username="testuser")
        self.assertEqual(bookshelf.objects.all().count(), 1)
        self.assertEqual(bookshelf.objects.filter(user=user).count(), 1)
        self.assertEqual(bookshelf.objects.get(user=user).book.title, "Книга")

    def test_book_relations_are_unique(self) -> None:
        book = Book.objects.get(title="Книга")
        duplicate_relations = (
            lambda: bauthor.objects.create(book=book, author=book.authors.get()),
            lambda: bgenre.objects.create(book=book, genre=book.genres.get()),
            lambda: bseries.objects.create(book=book, ser=book.series.get(), ser_no=1),
            lambda: bookshelf.objects.create(
                user=User.objects.get(username="testuser"), book=book
            ),
        )

        for create_duplicate in duplicate_relations:
            with self.assertRaises(IntegrityError), transaction.atomic():
                create_duplicate()

    def test_entities_are_unique(self) -> None:
        book = Book.objects.get(title="Книга")
        catalog = book.catalog
        duplicate_entities = (
            lambda: Book.objects.create(
                filename=book.filename,
                filesize=book.filesize,
                format=book.format,
                catalog=catalog,
                docdate=book.docdate,
                lang=book.lang,
                title="Другая книга",
                annotation="",
            ),
            lambda: Catalog.objects.create(
                parent=None, cat_name="duplicate", path=catalog.path, cat_type=1
            ),
            lambda: Author.objects.create(full_name="Шелепнев Дмитрий"),
            lambda: Genre.objects.create(
                genre="fantastic0", section="other", subsection="other"
            ),
            lambda: Series.objects.create(ser="mywork"),
        )

        for create_duplicate in duplicate_entities:
            with self.assertRaises(IntegrityError), transaction.atomic():
                create_duplicate()

    def test_entity_keys_are_case_sensitive(self) -> None:
        Author.objects.create(full_name="шелепнев дмитрий")
        Genre.objects.create(genre="Fantastic0", section="other", subsection="other")
        Series.objects.create(ser="MyWork")

    def test_entity_keys_preserve_ignorable_unicode_characters(self) -> None:
        Series.objects.create(ser="Цветы любви")
        Series.objects.create(ser="Цветы люб\u00adви")

    def test_Counter(self) -> None:
        """Тестирование соответствия структуры модели Counter, менеджера \
CounterManager и работоспособности БД"""
        self.assertEqual(Counter.objects.get_counter(models.counter_allbooks), 1)
        self.assertEqual(Counter.objects.get_counter(models.counter_allauthors), 1)
        self.assertEqual(Counter.objects.get_counter(models.counter_allcatalogs), 1)
        self.assertEqual(Counter.objects.get_counter(models.counter_allgenres), 1)
        self.assertEqual(Counter.objects.get_counter(models.counter_allseries), 1)
