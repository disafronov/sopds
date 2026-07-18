# -*- coding: utf-8 -*-

from base64 import b64encode

import pytest
from django.http import HttpRequest
from pytest_mock import MockerFixture

from opds_catalog.middleware import BasicAuthMiddleware


@pytest.fixture
def middleware() -> BasicAuthMiddleware:
    return BasicAuthMiddleware()


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
    def test_auth_disabled_returns_none(
        self,
        mocker: MockerFixture,
        middleware: BasicAuthMiddleware,
        request_no_auth: HttpRequest,
    ) -> None:
        mocker.patch(
            "opds_catalog.middleware.config", type("C", (), {"SOPDS_AUTH": False})()
        )
        assert middleware.process_request(request_no_auth) is None

    def test_no_header_returns_401(
        self,
        mocker: MockerFixture,
        middleware: BasicAuthMiddleware,
        request_no_auth: HttpRequest,
    ) -> None:
        mocker.patch(
            "opds_catalog.middleware.config", type("C", (), {"SOPDS_AUTH": True})()
        )
        response = middleware.process_request(request_no_auth)
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
        response = middleware.process_request(request_with_auth)
        assert response is None  # authenticated, continue

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
        response = middleware.process_request(request_with_auth)
        assert response is not None
        assert response.status_code == 401

    def test_unauthed_response(self, middleware: BasicAuthMiddleware) -> None:
        response = middleware.unauthed()
        assert response.status_code == 401
        assert "WWW-Authenticate" in response
