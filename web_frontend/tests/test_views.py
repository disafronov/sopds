# -*- coding: utf-8 -*-

from typing import Any

import pytest
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, QueryDict
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse
from django.utils.translation import override
from pytest_mock import MockerFixture

from opds_catalog.models import Genre, Series, lang_menu


@pytest.fixture
def user(db: Any) -> User:
    return User.objects.create_user(username="testuser", password="testpass")


@pytest.fixture
def auth_client(client: Client, user: User) -> Client:
    client.force_login(user)
    return client


def make_anon_request() -> HttpRequest:
    request = HttpRequest()
    request.method = "GET"
    request.GET = QueryDict("")
    request.user = type("U", (), {"is_authenticated": False})()
    return request


def make_auth_request() -> HttpRequest:
    request = HttpRequest()
    request.method = "GET"
    request.GET = QueryDict("")
    request.user = type("U", (), {"is_authenticated": True})()
    return request


def _set_auth(mocker: MockerFixture, value: bool) -> None:
    """Override constance config.SOPDS_AUTH without hitting the DB.

    constance Config stores SOPDS_AUTH via a LazyObject proxy whose
    ``__getattr__`` performs a DB lookup. Writing the attribute directly into
    the instance ``__dict__`` short-circuits that lookup, so the subsequent
    ``patch.object`` (and its teardown ``delattr``) operate on a plain
    attribute and never touch the database.
    """
    from web_frontend import views

    object.__setattr__(views.config, "SOPDS_AUTH", value)  # type: ignore[attr-defined]
    mocker.patch.object(views.config, "SOPDS_AUTH", value)  # type: ignore[attr-defined]


class TestSopdsProcessor:
    """Tests for sopds_processor() context processor."""

    def test_processor_without_auth(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        _set_auth(mocker, False)
        request = make_anon_request()
        ctx = views.sopds_processor(request)
        assert "app_title" in ctx
        assert "sopds_auth" in ctx
        assert ctx["sopds_auth"] is False

    def test_processor_with_auth(
        self, db: Any, user: User, mocker: MockerFixture
    ) -> None:
        from web_frontend import views

        _set_auth(mocker, True)
        request = make_auth_request()
        request.user = user
        ctx = views.sopds_processor(request)
        assert ctx["sopds_auth"] is True


@pytest.mark.parametrize("current", ["book", "author", "series"])
def test_menu_marks_selected_alphabet_group_as_active(current: str) -> None:
    html = render_to_string(
        "sopds_menu.html",
        {
            "alphabet": True,
            "current": current,
            "lang_code": 1,
            "lang_menu": lang_menu,
        },
    )

    assert html.count('class="active"') == 2


def test_russian_menu_and_book_metadata_use_distinct_translations() -> None:
    with override("ru"):
        menu = render_to_string(
            "sopds_menu.html",
            {"alphabet": False, "current": "book"},
        )
        books = render_to_string(
            "sopds_books_opds.html",
            {
                "opds_adapter": {
                    "feed_url": "/opds/search/books/i/5/",
                    "page_url": "/web/search/books/",
                },
                "cache_t": 0,
            },
        )

    assert ">Авторы<" in menu
    assert ">Серии<" in menu
    assert ">Жанры<" in menu
    assert 'data-authors-label="Авторы"' in books
    assert 'data-series-label="Серии"' in books
    assert 'data-genres-label="Жанры"' in books


class TestSearchBooksView:
    """Tests for SearchBooksView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.SearchBooksView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.SearchBooksView(make_auth_request())
        assert response.status_code == 200

    def test_pagination_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("page=2")
        response = views.SearchBooksView(request)
        assert response.status_code == 200

    def test_search_query_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("search=dune")
        response = views.SearchBooksView(request)
        assert response.status_code == 200

    def test_genre_search_resolves_card_link_to_opds_id(
        self, db: Any, mocker: MockerFixture
    ) -> None:
        from web_frontend import views

        genre = Genre.objects.create(
            genre="sf_detective", section="sf", subsection="sf_detective"
        )
        rendered: dict[str, Any] = {}

        def capture_render(
            request: HttpRequest, template: str, context: dict[str, Any]
        ) -> HttpResponse:
            rendered.update(context)
            return HttpResponse("ok")

        mocker.patch.object(views, "render", side_effect=capture_render)
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("searchtype=g&searchterms=sf_detective")

        response = views.SearchBooksView(request)

        assert response.status_code == 200
        assert rendered["opds_adapter"]["feed_url"].endswith(
            f"/opds/search/books/g/{genre.id}/"
        )

    @pytest.mark.parametrize(
        ("searchtype", "searchobject", "breadcrumb"),
        [
            ("b", "title", "Search by title"),
            ("a", "author", "Search by author"),
            ("s", "series", "Search by series"),
            ("g", "genre", "Search by genre"),
            ("u", "title", "Bookshelf"),
        ],
    )
    def test_search_modes_build_expected_context(
        self,
        db: Any,
        mocker: MockerFixture,
        searchtype: str,
        searchobject: str,
        breadcrumb: str,
    ) -> None:
        from web_frontend import views

        rendered: dict[str, Any] = {}

        def capture_render(
            request: HttpRequest, template: str, context: dict[str, Any]
        ) -> HttpResponse:
            rendered.update(context)
            return HttpResponse("ok")

        mocker.patch.object(views, "render", side_effect=capture_render)
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict(f"searchtype={searchtype}&searchterms=missing")

        response = views.SearchBooksView(request)

        assert response.status_code == 200
        assert rendered["searchobject"] == searchobject
        assert breadcrumb in [str(part) for part in rendered["breadcrumbs"]]
        if searchtype == "u":
            assert rendered["isbookshelf"] == 1


class TestLoginView:
    """Tests for LoginView()."""

    def test_get_login_page(self, db: Any, client: Client) -> None:
        response = client.get("/web/login/")
        # Either 200 (login page) or redirect to login
        assert response.status_code in (200, 302)

    def test_post_invalid_credentials(self, db: Any, client: Client) -> None:
        response = client.post("/web/login/", {"username": "nope", "password": "wrong"})
        assert response.status_code in (200, 302, 403)

    def test_post_valid_credentials(self, db: Any, client: Client, user: User) -> None:
        response = client.post(
            "/web/login/", {"username": "testuser", "password": "testpass"}
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/web/"

    def test_redirects_to_session_page_after_login(
        self,
        db: Any,
        client: Client,
        user: User,
        mocker: MockerFixture,
    ) -> None:
        _set_auth(mocker, True)

        response = client.get("/web/search/books/?searchtype=u")

        assert response.status_code == 302
        assert response.headers["Location"] == "/web/login/"

        response = client.post(
            "/web/login/",
            {"username": "testuser", "password": "testpass"},
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/web/search/books/?searchtype=u"


class TestLogoutView:
    """Tests for LogoutView()."""

    def test_logout(self, db: Any, auth_client: Client) -> None:
        response = auth_client.get("/web/logout/")
        assert response.status_code in (200, 302, 301)


class TestHello:
    """Tests for hello()."""

    def test_hello_returns_200_when_auth_is_disabled(
        self,
        db: Any,
        client: Client,
        user: User,
        mocker: MockerFixture,
    ) -> None:
        _set_auth(mocker, False)
        response = client.get("/web/")
        content = response.content.decode()

        assert response.status_code == 200
        assert "Hello Guest!" in content
        assert content.count('href="/"') >= 2
        assert 'href="/opds/"' in content
        assert "https://github.com/disafronov/sopds/issues" in content
        assert "js/jquery.min.js" in content
        assert "js/what-input.min.js" in content
        assert "js/foundation.min.js" in content
        assert "js/vendor/jquery.js" not in content
        assert "js/vendor/what-input.js" not in content

        client.force_login(user)
        auth_content = client.get("/web/").content.decode()
        assert "Hello testuser!" in auth_content

    def test_authenticated_navigation_uses_inline_icons(
        self,
        db: Any,
        auth_client: Client,
        mocker: MockerFixture,
    ) -> None:
        _set_auth(mocker, True)

        content = auth_client.get("/web/").content.decode()

        assert '<img class="nav-icon"' in content
        assert "images/fi-torsos.svg" in content
        assert "foundation-icons" not in content
        assert '<i class="fi-torsos"' not in content

    def test_hello_redirects_to_login_when_auth_is_enabled(
        self,
        db: Any,
        client: Client,
        mocker: MockerFixture,
    ) -> None:
        _set_auth(mocker, True)

        response = client.get("/web/")

        assert response.status_code == 302
        assert response["Location"] == "/web/login/"


class TestHandler403:
    """Tests for handler403()."""

    def test_returns_403(self, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(
            views, "render", return_value=HttpResponse("forbidden", status=403)
        )
        response = views.handler403(make_anon_request(), {})
        assert response.status_code == 403


class TestSearchSeriesView:
    """Tests for SearchSeriesView()."""

    def test_exact_series_redirects_directly_to_books(self, db: Any) -> None:
        from web_frontend import views

        series = Series.objects.create(ser="")
        request = make_anon_request()
        request.GET = QueryDict("searchtype=e&searchterms=__sopds_empty__")

        response = views.SearchSeriesView(request)

        assert response.status_code == 302
        assert response["Location"] == (
            f"{reverse('web:searchbooks')}?searchtype=s&searchterms={series.pk}"
        )

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.SearchSeriesView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.SearchSeriesView(make_auth_request())
        assert response.status_code == 200

    def test_pagination_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("page=3")
        response = views.SearchSeriesView(request)
        assert response.status_code == 200

    def test_search_query_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("searchterms=foundation")
        response = views.SearchSeriesView(request)
        assert response.status_code == 200


class TestSearchAuthorsView:
    """Tests for SearchAuthorsView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.SearchAuthorsView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.SearchAuthorsView(make_auth_request())
        assert response.status_code == 200

    def test_pagination_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("page=4")
        response = views.SearchAuthorsView(request)
        assert response.status_code == 200

    def test_search_query_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("searchterms=asimov")
        response = views.SearchAuthorsView(request)
        assert response.status_code == 200


@pytest.mark.parametrize(
    ("view", "model_name", "feed_url", "entity", "page_url"),
    [
        (
            "SearchAuthorsView",
            "Author",
            "/opds/search/authors/m/name/2/",
            "author",
            "/web/search/authors/",
        ),
        (
            "SearchSeriesView",
            "Series",
            "/opds/search/series/m/name/2/",
            "series",
            "/web/search/series/",
        ),
    ],
)
def test_entity_search_views_adapt_public_opds_feeds(
    db: Any,
    mocker: MockerFixture,
    view: str,
    model_name: str,
    feed_url: str,
    entity: str,
    page_url: str,
) -> None:
    from web_frontend import views

    rendered: dict[str, Any] = {}

    def capture_render(
        request: HttpRequest, template: str, context: dict[str, Any]
    ) -> HttpResponse:
        rendered.update(context)
        return HttpResponse("ok")

    mocker.patch.object(views, "render", side_effect=capture_render)
    none = mocker.patch.object(getattr(views, model_name).objects, "none")
    _set_auth(mocker, False)
    request = make_anon_request()
    request.GET = QueryDict("searchtype=m&searchterms=name&page=2")

    response = getattr(views, view)(request)

    assert response.status_code == 200
    none.assert_not_called()
    assert rendered["opds_adapter"]["feed_url"] == feed_url
    assert rendered["opds_adapter"]["entity"] == entity
    assert rendered["opds_adapter"]["page_url"] == page_url


class TestCatalogsView:
    """Tests for CatalogsView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.CatalogsView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.CatalogsView(make_auth_request())
        assert response.status_code == 200

    def test_pagination_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("page=2")
        response = views.CatalogsView(request)
        assert response.status_code == 200

    def test_cat_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("cat=1")
        response = views.CatalogsView(request)
        assert response.status_code == 200


class TestBooksView:
    """Tests for BooksView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.BooksView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.BooksView(make_auth_request())
        assert response.status_code == 200

    def test_lang_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1")
        response = views.BooksView(request)
        assert response.status_code == 200

    def test_lang_and_chars_params(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1&chars=a")
        response = views.BooksView(request)
        assert response.status_code == 200


class TestAuthorsView:
    """Tests for AuthorsView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.AuthorsView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.AuthorsView(make_auth_request())
        assert response.status_code == 200

    def test_lang_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1")
        response = views.AuthorsView(request)
        assert response.status_code == 200

    def test_lang_and_chars_params(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1&chars=b")
        response = views.AuthorsView(request)
        assert response.status_code == 200


class TestSeriesView:
    """Tests for SeriesView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.SeriesView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.SeriesView(make_auth_request())
        assert response.status_code == 200

    def test_lang_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1")
        response = views.SeriesView(request)
        assert response.status_code == 200

    def test_lang_and_chars_params(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1&chars=c")
        response = views.SeriesView(request)
        assert response.status_code == 200


@pytest.mark.parametrize(
    ("view_name", "view", "model_name", "feed_url", "selector_url", "search_url"),
    [
        (
            "book",
            "BooksView",
            "Book",
            "/opds/books/1/AB/",
            "/web/book/",
            "/web/search/books/",
        ),
        (
            "author",
            "AuthorsView",
            "Author",
            "/opds/authors/1/AB/",
            "/web/author/",
            "/web/search/authors/",
        ),
        (
            "series",
            "SeriesView",
            "Series",
            "/opds/series/1/AB/",
            "/web/series/",
            "/web/search/series/",
        ),
    ],
)
def test_selector_views_adapt_public_opds_feeds(
    db: Any,
    mocker: MockerFixture,
    view_name: str,
    view: str,
    model_name: str,
    feed_url: str,
    selector_url: str,
    search_url: str,
) -> None:
    from web_frontend import views

    rendered: dict[str, Any] = {}

    def capture_render(
        request: HttpRequest, template: str, context: dict[str, Any]
    ) -> HttpResponse:
        rendered.update(context)
        return HttpResponse("ok")

    mocker.patch.object(views, "render", side_effect=capture_render)
    raw = mocker.patch.object(getattr(views, model_name).objects, "raw")
    _set_auth(mocker, False)
    request = make_anon_request()
    request.GET = QueryDict("lang=1&chars=ab")

    response = getattr(views, view)(request)

    assert response.status_code == 200
    raw.assert_not_called()
    assert rendered["current"] == view_name
    assert rendered["opds_adapter"]["feed_url"] == feed_url
    assert rendered["opds_adapter"]["selector_url"] == selector_url
    assert rendered["opds_adapter"]["search_url"] == search_url


class TestGenresView:
    """Tests for GenresView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.GenresView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.GenresView(make_auth_request())
        assert response.status_code == 200

    def test_section_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        Genre.objects.create(id=1, genre="Fiction", section="Fiction", subsection="")
        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("section=1")
        response = views.GenresView(request)
        assert response.status_code == 200

    def test_pagination_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("page=2")
        response = views.GenresView(request)
        assert response.status_code == 200

    def test_adapts_public_opds_feed_without_genre_query(
        self, db: Any, mocker: MockerFixture
    ) -> None:
        from web_frontend import views

        rendered: dict[str, Any] = {}

        def capture_render(
            request: HttpRequest, template: str, context: dict[str, Any]
        ) -> HttpResponse:
            rendered.update(context)
            return HttpResponse("ok")

        mocker.patch.object(views, "render", side_effect=capture_render)
        get = mocker.patch("web_frontend.views.Genre.objects.get")
        filter_genres = mocker.patch("web_frontend.views.Genre.objects.filter")
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("section=232")

        response = views.GenresView(request)

        assert response.status_code == 200
        get.assert_not_called()
        filter_genres.assert_not_called()
        assert rendered["opds_adapter"]["feed_url"] == "/opds/genres/232/"
        assert rendered["opds_adapter"]["selector_url"] == "/web/genre/"
        assert rendered["opds_adapter"]["search_url"] == "/web/search/books/"


class TestBSDelView:
    """Tests for BSDelView()."""

    def test_returns_redirect_authenticated(self, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "reverse", return_value="/search/books/")
        bookshelf_filter = mocker.MagicMock(delete=mocker.MagicMock())
        mocker.patch(
            "web_frontend.views.bookshelf.objects.filter",
            return_value=bookshelf_filter,
        )
        request = make_auth_request()
        request.method = "POST"
        request.POST = QueryDict("book=1")
        response = views.BSDelView(request)
        assert response.status_code in (301, 302)

    def test_anonymous_redirects(self, mocker: MockerFixture) -> None:
        from web_frontend import views

        request = make_anon_request()
        request.method = "POST"
        request.path = "/web/bs/delete/"
        request.META = {"HTTP_HOST": "testserver"}
        response = views.BSDelView(request)
        assert response.status_code == 302


class TestBSClearView:
    """Tests for BSClearView()."""

    def test_returns_redirect_authenticated(self, mocker: MockerFixture) -> None:
        from web_frontend import views

        mocker.patch.object(views, "reverse", return_value="/search/books/")
        bookshelf_filter = mocker.MagicMock(delete=mocker.MagicMock())
        mocker.patch(
            "web_frontend.views.bookshelf.objects.filter",
            return_value=bookshelf_filter,
        )
        request = make_auth_request()
        request.method = "POST"
        response = views.BSClearView(request)
        assert response.status_code in (301, 302)

    def test_anonymous_redirects(self, mocker: MockerFixture) -> None:
        from web_frontend import views

        request = make_anon_request()
        request.method = "POST"
        request.path = "/web/bs/clear/"
        request.META = {"HTTP_HOST": "testserver"}
        response = views.BSClearView(request)
        assert response.status_code == 302
