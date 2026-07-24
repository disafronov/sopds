# -*- coding: utf-8 -*-

from base64 import b64encode
from typing import Any, cast

import pytest
from constance import config
from django.http import HttpRequest, HttpResponse
from django.test import Client
from django.urls import resolve
from pytest_mock import MockerFixture

from opds_catalog.middleware import BasicAuthMiddleware


@pytest.fixture
def middleware() -> BasicAuthMiddleware:
    return BasicAuthMiddleware(lambda request: HttpResponse())


@pytest.fixture
def request_with_auth() -> HttpRequest:
    request = HttpRequest()
    request.META = {}
    credentials = b64encode(b"user:pass").decode()
    request.META["HTTP_AUTHORIZATION"] = f"Basic {credentials}"
    request.user = type("U", (), {"is_authenticated": True})()
    return request


@pytest.fixture
def request_no_auth() -> HttpRequest:
    request = HttpRequest()
    request.META = {}
    request.user = type("U", (), {"is_authenticated": False})()
    return request


class TestBasicAuthMiddleware:
    def test_auth_disabled_allows_opds(
        self,
        mocker: MockerFixture,
        middleware: BasicAuthMiddleware,
        request_no_auth: HttpRequest,
    ) -> None:
        mocker.patch(
            "opds_catalog.middleware.config", type("C", (), {"SOPDS_AUTH": False})()
        )
        request_no_auth.resolver_match = resolve("/opds/")
        assert middleware.process_view(request_no_auth, object(), (), {}) is None

    def test_no_header_returns_401(
        self,
        middleware: BasicAuthMiddleware,
        request_no_auth: HttpRequest,
    ) -> None:
        response = middleware.authenticate(request_no_auth)
        assert response is not None
        assert response.status_code == 401

    def test_valid_basic_auth(
        self,
        mocker: MockerFixture,
        middleware: BasicAuthMiddleware,
        request_with_auth: HttpRequest,
    ) -> None:
        mocker.patch(
            "opds_catalog.middleware.config", type("C", (), {"SOPDS_AUTH": True})()
        )

        class _User:
            is_active = True

        user = _User()
        mocker.patch("django.contrib.auth.authenticate", return_value=user)
        mocker.patch("django.contrib.auth.login")
        response = middleware.authenticate(request_with_auth)
        assert response is None  # authenticated, continue
        assert request_with_auth.user is cast(Any, user)

    def test_invalid_basic_auth(
        self,
        mocker: MockerFixture,
        middleware: BasicAuthMiddleware,
        request_with_auth: HttpRequest,
    ) -> None:
        mocker.patch(
            "opds_catalog.middleware.config", type("C", (), {"SOPDS_AUTH": True})()
        )
        mocker.patch("django.contrib.auth.authenticate", return_value=None)
        response = middleware.authenticate(request_with_auth)
        assert response is not None
        assert response.status_code == 401

    @pytest.mark.parametrize(
        "header",
        ["Bearer token", "Basic invalid!", "Basic dXNlcg=="],
    )
    def test_malformed_authorization_returns_401(
        self,
        middleware: BasicAuthMiddleware,
        request_no_auth: HttpRequest,
        header: str,
    ) -> None:
        request_no_auth.META["HTTP_AUTHORIZATION"] = header
        response = middleware.authenticate(request_no_auth)
        assert response is not None
        assert response.status_code == 401

    def test_opds_anonymous_request_uses_basic_auth(
        self,
        mocker: MockerFixture,
        middleware: BasicAuthMiddleware,
        request_no_auth: HttpRequest,
    ) -> None:
        mocker.patch(
            "opds_catalog.middleware.config", type("C", (), {"SOPDS_AUTH": True})()
        )
        request_no_auth.resolver_match = resolve("/opds/download/1/0/")
        authenticate = mocker.patch.object(
            middleware, "authenticate", return_value=HttpResponse(status=401)
        )

        response = middleware.process_view(request_no_auth, object(), (), {})

        assert response is not None
        assert response.status_code == 401
        authenticate.assert_called_once_with(request_no_auth)

    def test_web_anonymous_request_redirects_to_login(
        self,
        mocker: MockerFixture,
        middleware: BasicAuthMiddleware,
        request_no_auth: HttpRequest,
    ) -> None:
        mocker.patch(
            "opds_catalog.middleware.config", type("C", (), {"SOPDS_AUTH": True})()
        )
        request_no_auth.path = "/web/"
        request_no_auth.META["HTTP_HOST"] = "testserver"
        request_no_auth.resolver_match = resolve("/web/")

        response = middleware.process_view(request_no_auth, object(), (), {})

        assert response is not None
        assert response.status_code == 302
        assert response["Location"].startswith("/web/login/?next=")

    @pytest.mark.parametrize(
        "path",
        ["/web/login/", "/admin/"],
    )
    def test_login_and_admin_keep_their_own_access_policy(
        self,
        mocker: MockerFixture,
        middleware: BasicAuthMiddleware,
        request_no_auth: HttpRequest,
        path: str,
    ) -> None:
        mocker.patch(
            "opds_catalog.middleware.config", type("C", (), {"SOPDS_AUTH": True})()
        )
        request_no_auth.resolver_match = resolve(path)

        assert middleware.process_view(request_no_auth, object(), (), {}) is None

    def test_unauthed_response(self, middleware: BasicAuthMiddleware) -> None:
        response = middleware.unauthed()
        assert response.status_code == 401
        assert "WWW-Authenticate" in response

    @pytest.mark.django_db
    def test_admin_requires_login_when_catalog_auth_is_disabled(
        self,
        client: Client,
    ) -> None:
        original_auth = config.SOPDS_AUTH
        config.SOPDS_AUTH = False

        try:
            response = client.get("/admin/")
        finally:
            config.SOPDS_AUTH = original_auth

        assert response.status_code == 302
        assert response["Location"].startswith("/admin/login/")
