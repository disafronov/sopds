import base64
import binascii
from typing import Optional

from constance import config
from django.contrib import auth
from django.http import HttpRequest, HttpResponse
from django.middleware.cache import (
    FetchFromCacheMiddleware as DjangoFetchFromCacheMiddleware,
)
from django.shortcuts import redirect
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import escape_leading_slashes

from web_backend.settings import LOGIN_NEXT_SESSION_KEY


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
        view_func: object,
        _view_args: object,
        _view_kwargs: object,
    ) -> Optional[HttpResponse]:
        from web_backend.views import LoginView

        if not config.SOPDS_AUTH or request.user.is_authenticated:
            return None

        resolver_match = request.resolver_match
        if resolver_match is None:
            return None
        if resolver_match.namespace == "opds":
            return self.authenticate(request)
        if resolver_match.namespace == "web" and view_func is not LoginView:
            request.session[LOGIN_NEXT_SESSION_KEY] = escape_leading_slashes(
                request.get_full_path()
            )
            return redirect("web:login")
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
