# -*- coding: utf-8 -*-

from constance import config
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import override, pgettext

from opds_catalog import opdsdb
from opds_catalog.models import Author, Book, Genre, Series


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

    def test_MainFeed_uses_relative_internal_links(self) -> None:
        response = Client().get(
            reverse("opds:main"),
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_X_FORWARDED_HOST="library.example",
        )

        content = response.content.decode()
        self.assertIn("<id>urn:sopds:feed:/opds/</id>", content)
        self.assertIn('href="/opds/"', content)
        self.assertIn('href="/opds/catalogs/"', content)
        self.assertNotIn("library.example", content)

    def test_MainFeed_empty_bookshelf_remains_linked(self) -> None:
        config.SOPDS_AUTH = True
        user = User.objects.create_user(username="reader", password="password")
        client = Client()
        client.force_login(user)

        content = client.get(reverse("opds:main")).content.decode()

        self.assertIn("reader Book shelf", content)
        self.assertIn('rel="http://opds-spec.org/shelf"', content)
        self.assertIn('href="/opds/search/books/u/0/"', content)

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
        self.assertIn("/static/images/favicon.ico", response.content.decode())
        self.assertIn(
            'template="/opds/search/{searchTerms}/"',
            response.content.decode(),
        )

    def test_MainFeed_uses_legacy_search_template(self) -> None:
        content = Client().get(reverse("opds:main")).content.decode()

        self.assertIn('href="/opds/search/{searchTerms}/"', content)
        self.assertIn('rel="search"', content)
        self.assertIn('type="application/atom+xml"', content)

    def test_SearchTypes(self) -> None:
        c = Client()
        response = c.get("/opds/search/Драк/")
        self.assertEqual(response.status_code, 200)
        response = c.get(reverse("opds:searchtypes", kwargs={"searchterms": "Драк"}))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'href="/opds/search/%D0%94%D1%80%D0%B0%D0%BA/" rel="self"',
            response.content.decode(),
        )
        self.assertIn(
            'href="/opds/search/{searchTerms}/" rel="search"',
            response.content.decode(),
        )
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

    def test_empty_names_use_placeholders_in_alphabet_feeds(self) -> None:
        Book.objects.filter(pk=5).update(title="", lang_code=9)
        Book.objects.filter(pk=6).update(title="", lang_code=9)
        Book.objects.filter(pk=7).update(title=" ", lang_code=9)
        Book.objects.get(pk=5).authors.clear()
        Book.objects.get(pk=6).authors.clear()
        Author.objects.filter(pk=5).update(full_name="", lang_code=9)
        Author.objects.filter(pk=6).update(full_name=" ", lang_code=9)
        empty_series = Series.objects.create(ser="", lang_code=9)
        Series.objects.create(ser=" ", lang_code=9)
        linked_genre = Genre.objects.create(
            section="test",
            subsection="test_genre",
        )
        book_with_series = Book.objects.get(pk=5)
        book_with_series.series.add(empty_series)
        book_with_series.genres.add(linked_genre)
        book_with_series.bseries_set.filter(ser=empty_series).update(ser_no=3)

        client = Client()
        routes = {
            "char_books": _("Untitled"),
            "char_authors": _("Unknown author"),
            "char_series": _("Unnamed series"),
        }
        for lang_code in (0, 9):
            for route_name, placeholder in routes.items():
                with self.subTest(route_name=route_name, lang_code=lang_code):
                    response = client.get(
                        reverse(f"opds:{route_name}", kwargs={"lang_code": lang_code})
                    )
                    content = response.content.decode()
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(placeholder, content)
                    self.assertIn("__sopds_empty__", content)
                    if lang_code == 9:
                        self.assertIn("%20", content)
                        self.assertLess(
                            content.index("__sopds_empty__"), content.index("%20")
                        )

        search_routes = {
            "searchbooks": _("Untitled"),
            "searchauthors": _("Unknown author"),
            "searchseries": _("Unnamed series"),
        }
        for route_name, placeholder in search_routes.items():
            with self.subTest(route_name=route_name):
                response = client.get(
                    reverse(
                        f"opds:{route_name}",
                        kwargs={
                            "searchtype": "e",
                            "searchterms": "__sopds_empty__",
                        },
                    )
                )
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                self.assertIn(placeholder, content)
                if route_name == "searchbooks":
                    self.assertEqual(content.count("<title>Untitled</title>"), 2)
                    self.assertIn("<id>b:5</id>", content)
                    self.assertIn("<id>b:6</id>", content)
                    self.assertNotIn("Series: &lt;/b&gt;", content)
                    self.assertNotIn("No in Series:", content)
                    self.assertNotIn("Book name:", content)
                    self.assertNotIn("File: &lt;/b&gt;", content)
                    self.assertNotIn("Changes date:", content)
                    self.assertIn(
                        f'href="/opds/search/books/s/{empty_series.pk}/"',
                        content,
                    )
                    self.assertIn(
                        'rel="related" title="Series: Unnamed series [3]"',
                        content,
                    )
                    self.assertIn(
                        f'href="/opds/search/books/g/{linked_genre.pk}/"',
                        content,
                    )
                    self.assertLess(
                        content.index('title="Series: Unnamed series [3]"'),
                        content.index('title="Genre: test_genre"'),
                    )
                    self.assertNotIn("<sopds:series", content)
                    self.assertIn('length="503533"', content)
                    self.assertIn('type="application/fb2"', content)
                    self.assertNotIn('type="application/fb2+xml"', content)
                    self.assertNotIn("<sopds:filename>", content)
                    self.assertNotIn("<sopds:filesize>", content)
                    self.assertNotIn("<sopds:annotation>", content)
                    self.assertNotIn("<sopds:id>", content)
                    self.assertIn("<dcterms:issued>", content)
                    self.assertNotIn("<sopds:docdate>", content)

                    with override("ru"):
                        self.assertEqual(
                            pgettext(
                                "book metadata link",
                                "Series: %(series)s",
                            )
                            % {"series": "Серия без названия"},
                            "Серия: Серия без названия",
                        )
                        self.assertEqual(
                            pgettext(
                                "book metadata link",
                                "Genre: %(genre)s",
                            )
                            % {"genre": "fantasy"},
                            "Жанр: fantasy",
                        )

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

    def test_GenresFeed_subsection_links_to_parent(self) -> None:
        section = Genre.objects.get(id=232).section
        content = (
            Client()
            .get(reverse("opds:genres", kwargs={"section": 232}))
            .content.decode()
        )

        self.assertIn('href="/opds/genres/" rel="up"', content)
        self.assertIn(f'title="{section}"', content)

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
        content = response.content.decode()
        self.assertNotIn("xmlns:sopds=", content)
        self.assertNotIn("<sopds:page>", content)
        self.assertNotIn("<sopds:pages>", content)
        self.assertIn('rel="first"', content)
        self.assertIn('rel="last"', content)
        self.assertNotIn("<sopds:cat-type>", content)
        self.assertNotIn('rel="alternate"', content)

    def test_SearchSeriesPage(self) -> None:
        c = Client()
        response = c.get("/opds/search/series/m/Драк/1/")
        self.assertEqual(response.status_code, 200)

    def test_auth_disabled_no_basic_auth_middleware(self) -> None:
        """When SOPDS_AUTH=False, BasicAuthMiddleware must not be called."""
        config.SOPDS_AUTH = False
        c = Client()
        response = c.get(reverse("opds:main"))
        self.assertEqual(response.status_code, 200)

    def test_auth_enabled_unauthenticated_returns_401(self) -> None:
        """When SOPDS_AUTH=True, unauthenticated request to feed returns 401."""
        config.SOPDS_AUTH = True
        c = Client()
        response = c.get(reverse("opds:main"))
        self.assertEqual(response.status_code, 401)
