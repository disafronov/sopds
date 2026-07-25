"""Browser timezone handling for web requests."""

from collections.abc import Callable
from urllib.parse import unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import timezone


class TimezoneMiddleware:
    """Activate the IANA timezone detected by the browser."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        tzname = unquote(request.COOKIES.get("timezone", ""))
        if tzname:
            try:
                timezone.activate(ZoneInfo(tzname))
                request.timezone_detected = True  # type: ignore[attr-defined]
            except (ZoneInfoNotFoundError, KeyError):
                timezone.deactivate()
                request.timezone_detected = False  # type: ignore[attr-defined]
        else:
            timezone.deactivate()
            request.timezone_detected = False  # type: ignore[attr-defined]

        return self.get_response(request)


def timezone_context(request: HttpRequest) -> dict[str, object]:
    """Expose browser timezone detection state to templates."""

    return {
        "timezone_detected": getattr(request, "timezone_detected", False),
        "server_timezone": settings.TIME_ZONE,
    }
