# -*- coding: utf-8 -*-

from typing import Any

import pytest
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, QueryDict
from django.test import Client
from pytest_mock import MockerFixture

from opds_catalog.models import Genre


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
    from web_backend import views

    object.__setattr__(views.config, "SOPDS_AUTH", value)  # type: ignore[attr-defined]
    mocker.patch.object(views.config, "SOPDS_AUTH", value)  # type: ignore[attr-defined]


class TestSopdsProcessor:
    """Tests for sopds_processor() context processor."""

    def test_processor_without_auth(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        _set_auth(mocker, False)
        request = make_anon_request()
        ctx = views.sopds_processor(request)
        assert "app_title" in ctx
        assert "sopds_auth" in ctx
        assert ctx["sopds_auth"] is False

    def test_processor_with_auth(
        self, db: Any, user: User, mocker: MockerFixture
    ) -> None:
        from web_backend import views

        _set_auth(mocker, True)
        request = make_auth_request()
        request.user = user
        ctx = views.sopds_processor(request)
        assert ctx["sopds_auth"] is True


class TestSopdsLoginDecorator:
    """Tests for sopds_login() decorator."""

    def test_decorator_with_auth_disabled(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        _set_auth(mocker, False)
        called: dict[str, bool] = {}

        @views.sopds_login(url="web:login")
        def protected(request: HttpRequest) -> HttpResponse:
            called["hit"] = True
            return HttpResponse("ok")

        request = make_anon_request()
        response = protected(request)
        assert called.get("hit") is True
        assert response.status_code == 200

    def test_decorator_with_auth_enabled_anonymous_redirects(
        self, db: Any, mocker: MockerFixture
    ) -> None:
        from web_backend import views

        _set_auth(mocker, True)
        mocker.patch.object(views, "reverse_lazy", return_value="/login/")

        @views.sopds_login(url="web:login")
        def protected(request: HttpRequest) -> HttpResponse:
            return HttpResponse("ok")

        request = make_anon_request()
        request.path = "/web/protected/"
        request.META = {"HTTP_HOST": "testserver"}
        response = protected(request)
        assert response.status_code == 302


class TestSearchBooksView:
    """Tests for SearchBooksView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.SearchBooksView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.SearchBooksView(make_auth_request())
        assert response.status_code == 200

    def test_pagination_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("page=2")
        response = views.SearchBooksView(request)
        assert response.status_code == 200

    def test_search_query_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("search=dune")
        response = views.SearchBooksView(request)
        assert response.status_code == 200

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
        from web_backend import views

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
        assert response.status_code in (200, 302, 301)

    def test_redirects_to_internal_next_url(
        self, db: Any, client: Client, user: User
    ) -> None:
        response = client.post(
            "/web/login/",
            {"username": "testuser", "password": "testpass"},
            query_params={"next": "/web/search/books/?searchtype=u"},
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/web/search/books/?searchtype=u"

    @pytest.mark.parametrize(
        "next_url",
        [
            "https://attacker.example/steal",
            "//attacker.example/steal",
        ],
    )
    def test_rejects_external_next_url(
        self, db: Any, client: Client, user: User, next_url: str
    ) -> None:
        response = client.post(
            "/web/login/",
            {"username": "testuser", "password": "testpass"},
            query_params={"next": next_url},
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/web/"


class TestLogoutView:
    """Tests for LogoutView()."""

    def test_logout(self, db: Any, auth_client: Client) -> None:
        response = auth_client.get("/web/logout/")
        assert response.status_code in (200, 302, 301)


class TestHello:
    """Tests for hello()."""

    def test_hello_returns_200(self, db: Any, client: Client) -> None:
        response = client.get("/web/")
        assert response.status_code in (200, 302)


class TestHandler403:
    """Tests for handler403()."""

    def test_returns_403(self, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(
            views, "render", return_value=HttpResponse("forbidden", status=403)
        )
        response = views.handler403(make_anon_request(), {})
        assert response.status_code == 403


class TestSearchSeriesView:
    """Tests for SearchSeriesView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.SearchSeriesView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.SearchSeriesView(make_auth_request())
        assert response.status_code == 200

    def test_pagination_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("page=3")
        response = views.SearchSeriesView(request)
        assert response.status_code == 200

    def test_search_query_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("searchterms=foundation")
        response = views.SearchSeriesView(request)
        assert response.status_code == 200


class TestSearchAuthorsView:
    """Tests for SearchAuthorsView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.SearchAuthorsView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.SearchAuthorsView(make_auth_request())
        assert response.status_code == 200

    def test_pagination_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("page=4")
        response = views.SearchAuthorsView(request)
        assert response.status_code == 200

    def test_search_query_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("searchterms=asimov")
        response = views.SearchAuthorsView(request)
        assert response.status_code == 200


class TestCatalogsView:
    """Tests for CatalogsView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.CatalogsView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.CatalogsView(make_auth_request())
        assert response.status_code == 200

    def test_pagination_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("page=2")
        response = views.CatalogsView(request)
        assert response.status_code == 200

    def test_cat_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("cat=1")
        response = views.CatalogsView(request)
        assert response.status_code == 200


class TestBooksView:
    """Tests for BooksView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.BooksView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.BooksView(make_auth_request())
        assert response.status_code == 200

    def test_lang_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1")
        response = views.BooksView(request)
        assert response.status_code == 200

    def test_lang_and_chars_params(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1&chars=a")
        response = views.BooksView(request)
        assert response.status_code == 200


class TestAuthorsView:
    """Tests for AuthorsView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.AuthorsView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.AuthorsView(make_auth_request())
        assert response.status_code == 200

    def test_lang_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1")
        response = views.AuthorsView(request)
        assert response.status_code == 200

    def test_lang_and_chars_params(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1&chars=b")
        response = views.AuthorsView(request)
        assert response.status_code == 200


class TestSeriesView:
    """Tests for SeriesView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.SeriesView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.SeriesView(make_auth_request())
        assert response.status_code == 200

    def test_lang_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1")
        response = views.SeriesView(request)
        assert response.status_code == 200

    def test_lang_and_chars_params(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("lang=1&chars=c")
        response = views.SeriesView(request)
        assert response.status_code == 200


class TestGenresView:
    """Tests for GenresView()."""

    def test_returns_200_anonymous(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        response = views.GenresView(make_anon_request())
        assert response.status_code == 200

    def test_returns_200_authenticated(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, True)
        response = views.GenresView(make_auth_request())
        assert response.status_code == 200

    def test_section_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        Genre.objects.create(id=1, genre="Fiction", section="Fiction", subsection="")
        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("section=1")
        response = views.GenresView(request)
        assert response.status_code == 200

    def test_pagination_param(self, db: Any, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "render", return_value=HttpResponse("ok"))
        _set_auth(mocker, False)
        request = make_anon_request()
        request.GET = QueryDict("page=2")
        response = views.GenresView(request)
        assert response.status_code == 200


class TestBSDelView:
    """Tests for BSDelView()."""

    def test_returns_redirect_authenticated(self, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "reverse", return_value="/search/books/")
        bookshelf_filter = mocker.MagicMock(delete=mocker.MagicMock())
        mocker.patch(
            "web_backend.views.bookshelf.objects.filter",
            return_value=bookshelf_filter,
        )
        request = make_auth_request()
        request.method = "POST"
        request.POST = QueryDict("book=1")
        response = views.BSDelView(request)
        assert response.status_code in (301, 302)

    def test_anonymous_redirects(self, mocker: MockerFixture) -> None:
        from web_backend import views

        request = make_anon_request()
        request.method = "POST"
        request.path = "/web/bs/delete/"
        request.META = {"HTTP_HOST": "testserver"}
        response = views.BSDelView(request)
        assert response.status_code == 302


class TestBSClearView:
    """Tests for BSClearView()."""

    def test_returns_redirect_authenticated(self, mocker: MockerFixture) -> None:
        from web_backend import views

        mocker.patch.object(views, "reverse", return_value="/search/books/")
        bookshelf_filter = mocker.MagicMock(delete=mocker.MagicMock())
        mocker.patch(
            "web_backend.views.bookshelf.objects.filter",
            return_value=bookshelf_filter,
        )
        request = make_auth_request()
        request.method = "POST"
        response = views.BSClearView(request)
        assert response.status_code in (301, 302)

    def test_anonymous_redirects(self, mocker: MockerFixture) -> None:
        from web_backend import views

        request = make_anon_request()
        request.method = "POST"
        request.path = "/web/bs/clear/"
        request.META = {"HTTP_HOST": "testserver"}
        response = views.BSClearView(request)
        assert response.status_code == 302
