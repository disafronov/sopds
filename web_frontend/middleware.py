"""Browser-session authentication for the web frontend."""

from __future__ import annotations

from typing import Optional

from constance import config
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import escape_leading_slashes

from web_frontend.settings import LOGIN_NEXT_SESSION_KEY


class WebAuthenticationMiddleware(MiddlewareMixin):
    """Redirect anonymous web requests to the frontend login page."""

    def process_view(
        self,
        request: HttpRequest,
        view_func: object,
        _view_args: object,
        _view_kwargs: object,
    ) -> Optional[HttpResponse]:
        if not config.SOPDS_AUTH or request.user.is_authenticated:
            return None

        resolver_match = request.resolver_match
        if resolver_match is None or resolver_match.namespace != "web":
            return None

        from web_frontend.views import LoginView

        if view_func is LoginView:
            return None

        request.session[LOGIN_NEXT_SESSION_KEY] = escape_leading_slashes(
            request.get_full_path()
        )
        return redirect("web:login")
