from typing import Any, cast

import pytest
from django.http import HttpRequest, HttpResponse
from django.urls import resolve
from pytest_mock import MockerFixture

from web_frontend.middleware import WebAuthenticationMiddleware


@pytest.fixture
def middleware() -> WebAuthenticationMiddleware:
    return WebAuthenticationMiddleware(lambda request: HttpResponse())


@pytest.fixture
def request_no_auth() -> HttpRequest:
    request = HttpRequest()
    request.user = type("U", (), {"is_authenticated": False})()
    request.session = cast(Any, {})
    return request


class TestWebAuthenticationMiddleware:
    def test_anonymous_web_request_redirects_to_login(
        self,
        mocker: MockerFixture,
        middleware: WebAuthenticationMiddleware,
        request_no_auth: HttpRequest,
    ) -> None:
        mocker.patch(
            "web_frontend.middleware.config",
            type("C", (), {"SOPDS_AUTH": True})(),
        )
        request_no_auth.path = "/web/"
        request_no_auth.META["HTTP_HOST"] = "testserver"
        request_no_auth.resolver_match = resolve("/web/")

        response = middleware.process_view(request_no_auth, object(), (), {})

        assert response is not None
        assert response.status_code == 302
        assert response["Location"] == "/web/login/"
        assert request_no_auth.session["sopds_login_next"] == "/web/"

    @pytest.mark.parametrize("path", ["/web/login/", "/opds/"])
    def test_login_and_other_namespaces_keep_their_own_policy(
        self,
        mocker: MockerFixture,
        middleware: WebAuthenticationMiddleware,
        request_no_auth: HttpRequest,
        path: str,
    ) -> None:
        mocker.patch(
            "web_frontend.middleware.config",
            type("C", (), {"SOPDS_AUTH": True})(),
        )
        request_no_auth.resolver_match = resolve(path)

        assert (
            middleware.process_view(
                request_no_auth,
                request_no_auth.resolver_match.func,
                (),
                {},
            )
            is None
        )
