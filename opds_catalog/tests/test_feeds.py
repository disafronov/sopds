# -*- coding: utf-8 -*-

from unittest.mock import patch

from constance import config
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.translation import gettext as _

from opds_catalog import opdsdb


class feedsTestCase(TestCase):
    fixtures = ["testdb.json"]

    def setUp(self) -> None:
        config.SOPDS_AUTH = False

    def test_MainFeed(self) -> None:
        c = Client()
        response = c.get("/opds/")
        self.assertEqual(response.status_code, 200)
        response = c.get(reverse("opds:main"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(_("By catalogs"), response.content.decode())
        self.assertIn(
            _("Catalogs: %(catalogs)s, books: %(books)s.")
            % {"catalogs": 2, "books": 4},
            response.content.decode(),
        )
        self.assertIn(
            _("Authors: %(authors)s.") % {"authors": 4}, response.content.decode()
        )
        self.assertIn(
            _("Genres: %(genres)s.") % {"genres": 4}, response.content.decode()
        )

    def test_CatalogsFeed(self) -> None:
        c = Client()
        response = c.get("/opds/catalogs/")
        self.assertEqual(response.status_code, 200)
        response = c.get(reverse("opds:catalogs"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("books.zip", response.content.decode())
        self.assertIn("The Sanctuary Sparrow", response.content.decode())

    def test_CatalogsFeedTree(self) -> None:
        c = Client()
        response = c.get("/opds/catalogs/4/")
        self.assertEqual(response.status_code, 200)
        response = c.get(reverse("opds:cat_tree", args=["4"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Драконьи Услуги", response.content.decode())
        self.assertIn("Китайски сладкиш с късметче", response.content.decode())
        self.assertIn("Любовь в жизни Обломова", response.content.decode())

    def test_CatalogsFeed_nonexistent_catalog_returns_404(self) -> None:
        c = Client()
        response = c.get(reverse("opds:cat_tree", args=["999999"]))
        self.assertEqual(response.status_code, 404)

    def test_OpenSearch(self) -> None:
        c = Client()
        response = c.get("/opds/search/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("www.sopds.ru", response.content.decode())

    def test_SearchTypes(self) -> None:
        c = Client()
        response = c.get("/opds/search/Драк/")
        self.assertEqual(response.status_code, 200)
        response = c.get(reverse("opds:searchtypes", kwargs={"searchterms": "Драк"}))
        self.assertEqual(response.status_code, 200)
        self.assertIn(_("Search by titles"), response.content.decode())

    def test_SearchBooks(self) -> None:
        c = Client()
        response = c.get("/opds/search/books/m/Драк/")
        self.assertEqual(response.status_code, 200)
        response = c.get(
            reverse(
                "opds:searchbooks", kwargs={"searchtype": "m", "searchterms": "рак"}
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Драконьи Услуги", response.content.decode())
        self.assertIn("Куприянов Денис", response.content.decode())
        response = c.get(
            reverse(
                "opds:searchbooks", kwargs={"searchtype": "b", "searchterms": "Драк"}
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Драконьи Услуги", response.content.decode())
        self.assertIn("Куприянов Денис", response.content.decode())
        response = c.get(
            reverse("opds:searchbooks", kwargs={"searchtype": "a", "searchterms": "8"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Драконьи Услуги", response.content.decode())
        self.assertIn("Куприянов Денис", response.content.decode())
        self.assertIn(
            _("All books by %(full_name)s") % {"full_name": "Куприянов Денис"},
            response.content.decode(),
        )
        self.assertIn("prose_contemporary", response.content.decode())
        self.assertIn("<category ", response.content.decode())

    def test_SearchAuthors(self) -> None:
        c = Client()
        response = c.get("/opds/search/authors/m/Логинов/")
        self.assertEqual(response.status_code, 200)
        response = c.get(
            reverse(
                "opds:searchauthors", kwargs={"searchtype": "m", "searchterms": "гинов"}
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Логинов Святослав", response.content.decode())
        response = c.get(
            reverse(
                "opds:searchauthors", kwargs={"searchtype": "b", "searchterms": "Лог"}
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Логинов Святослав", response.content.decode())

    def test_SearchGenres(self) -> None:
        # response = c.get('/opds/search/genres/antiq/')
        # self.assertEqual(response.status_code, 200)
        # self.assertIn("The Sanctuary Sparrow", response.content.decode())
        # self.assertIn("Peters Ellis", response.content.decode())
        pass

    def test_LangFeed(self) -> None:
        c = Client()
        response = c.get("/opds/books/")
        self.assertEqual(response.status_code, 200)
        response = c.get(reverse("opds:lang_books"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(_("Cyrillic"), response.content.decode())
        self.assertIn(_("Latin"), response.content.decode())
        self.assertIn(_("Digits"), response.content.decode())
        self.assertIn(_("Other symbols"), response.content.decode())
        self.assertIn(_("Show all"), response.content.decode())

    def test_BooksFeed(self) -> None:
        c = Client()
        response = c.get("/opds/books/0/")
        self.assertEqual(response.status_code, 200)
        if config.SOPDS_ALPHABET_MENU:
            response = c.get(reverse("opds:lang_books"))
            self.assertEqual(response.status_code, 200)
            self.assertIn(_("Cyrillic"), response.content.decode())
        response = c.get(reverse("opds:char_books", kwargs={"lang_code": 0}))
        self.assertIn("<title>T</title>", response.content.decode())

    def test_AuthorsFeed(self) -> None:
        c = Client()
        response = c.get("/opds/authors/0/")
        self.assertEqual(response.status_code, 200)
        if config.SOPDS_ALPHABET_MENU:
            response = c.get(reverse("opds:lang_authors"))
            self.assertEqual(response.status_code, 200)
            self.assertIn(_("Cyrillic"), response.content.decode())
        response = c.get(reverse("opds:char_authors", kwargs={"lang_code": 0}))
        self.assertIn("<title>P</title>", response.content.decode())

    def test_GenresFeed(self) -> None:
        c = Client()
        response = c.get("/opds/genres/")
        self.assertEqual(response.status_code, 200)
        response = c.get(reverse("opds:genres"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(opdsdb.unknown_genre_en, response.content.decode())
        response = c.get(reverse("opds:genres", kwargs={"section": 232}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("prose_contemporary", response.content.decode())

    def test_CatalogsFeedPage(self) -> None:
        c = Client()
        response = c.get("/opds/catalogs/4/1/")
        self.assertEqual(response.status_code, 200)
        response = c.get(reverse("opds:cat_page", args=["4", "1"]))
        self.assertEqual(response.status_code, 200)

    def test_SearchBooksPage(self) -> None:
        c = Client()
        response = c.get("/opds/search/books/m/Драк/1/")
        self.assertEqual(response.status_code, 200)

    def test_SearchAuthorsPage(self) -> None:
        c = Client()
        response = c.get("/opds/search/authors/m/Логинов/1/")
        self.assertEqual(response.status_code, 200)

    def test_SearchSeriesPage(self) -> None:
        c = Client()
        response = c.get("/opds/search/series/m/Драк/1/")
        self.assertEqual(response.status_code, 200)

    def test_auth_disabled_no_basic_auth_middleware(self) -> None:
        """When SOPDS_AUTH=False, BasicAuthMiddleware must not be called."""
        config.SOPDS_AUTH = False
        c = Client()
        with patch("opds_catalog.feeds.BasicAuthMiddleware") as mock_bau:
            response = c.get(reverse("opds:main"))
            self.assertEqual(response.status_code, 200)
            mock_bau.assert_not_called()

    def test_auth_enabled_unauthenticated_returns_401(self) -> None:
        """When SOPDS_AUTH=True, unauthenticated request to feed returns 401."""
        config.SOPDS_AUTH = True
        c = Client()
        response = c.get(reverse("opds:main"))
        self.assertEqual(response.status_code, 401)
