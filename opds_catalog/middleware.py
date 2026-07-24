import base64
import binascii
from typing import Optional

from constance import config
from django.contrib import auth
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.middleware.cache import (
    FetchFromCacheMiddleware as DjangoFetchFromCacheMiddleware,
)
from django.urls import reverse
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin


class BasicAuthMiddleware(MiddlewareMixin):
    header = "HTTP_AUTHORIZATION"

    def unauthed(self) -> HttpResponse:
        response = HttpResponse(
            """<html><title>Auth required</title><body>
                                <h1>Authorization Required</h1></body></html>""",
            content_type="text/html",
        )
        response["WWW-Authenticate"] = 'Basic realm="OPDS"'
        response.status_code = 401
        return response

    def process_view(
        self,
        request: HttpRequest,
        _view_func: object,
        _view_args: object,
        _view_kwargs: object,
    ) -> Optional[HttpResponse]:
        if not config.SOPDS_AUTH or request.user.is_authenticated:
            return None

        resolver_match = request.resolver_match
        if resolver_match is None:
            return None
        if resolver_match.namespace == "opds":
            return self.authenticate(request)
        if resolver_match.namespace == "web" and resolver_match.url_name != "login":
            return redirect_to_login(
                request.get_full_path(),
                reverse("web:login"),
            )
        return None

    def authenticate(self, request: HttpRequest) -> Optional[HttpResponse]:
        try:
            authentication = request.META[self.header]
            auth_meth, auth_data = authentication.split(" ", 1)
            if "basic" != auth_meth.lower():
                return self.unauthed()
            decoded = base64.b64decode(auth_data.strip(), validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (KeyError, ValueError, UnicodeDecodeError, binascii.Error):
            return self.unauthed()

        user = auth.authenticate(username=username, password=password)
        if user and user.is_active:
            request.user = user
            auth.login(request, user)
            return None

        return self.unauthed()


class SOPDSLocaleMiddleware(MiddlewareMixin):

    def process_request(self, request: HttpRequest) -> None:
        # LANG is a custom request attribute attached at runtime by this
        # middleware; django-stubs does not model it.
        request.LANG = config.SOPDS_LANGUAGE  # type: ignore[attr-defined]
        translation.activate(request.LANG)  # type: ignore[attr-defined]
        request.LANGUAGE_CODE = request.LANG  # type: ignore[attr-defined]


class FetchFromCacheMiddleware(DjangoFetchFromCacheMiddleware):

    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        if not request.user.is_authenticated:
            return None
        else:
            return super(FetchFromCacheMiddleware, self).process_request(request)
