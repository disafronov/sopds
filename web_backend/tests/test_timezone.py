from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, override_settings
from django.utils import timezone

from web_backend.timezone import TimezoneMiddleware, timezone_context


def empty_response(request: HttpRequest) -> HttpResponse:
    return HttpResponse()


class TestTimezoneMiddleware:
    def setup_method(self) -> None:
        self.factory = RequestFactory()
        get_response: Callable[[HttpRequest], HttpResponse] = empty_response
        self.middleware = TimezoneMiddleware(get_response)

    def test_no_cookie_deactivates_and_marks_undetected(self) -> None:
        request = self.factory.get("/")

        self.middleware(request)

        assert request.timezone_detected is False  # type: ignore[attr-defined]

    def test_valid_cookie_activates_and_marks_detected(self) -> None:
        request = self.factory.get("/", HTTP_COOKIE="timezone=Europe/Moscow")

        self.middleware(request)

        assert request.timezone_detected is True  # type: ignore[attr-defined]
        assert str(timezone.get_current_timezone()) == "Europe/Moscow"

    def test_percent_encoded_cookie_activates_timezone(self) -> None:
        request = self.factory.get("/", HTTP_COOKIE="timezone=Asia%2FYerevan")

        self.middleware(request)

        assert request.timezone_detected is True  # type: ignore[attr-defined]
        assert str(timezone.get_current_timezone()) == "Asia/Yerevan"

    def test_invalid_cookie_deactivates_and_marks_undetected(self) -> None:
        request = self.factory.get("/", HTTP_COOKIE="timezone=Not%2FA%2FTimezone")

        self.middleware(request)

        assert request.timezone_detected is False  # type: ignore[attr-defined]


class TestTimezoneContext:
    def setup_method(self) -> None:
        self.factory = RequestFactory()

    def test_returns_detection_state(self) -> None:
        request = self.factory.get("/")
        request.timezone_detected = True  # type: ignore[attr-defined]

        context = timezone_context(request)

        assert context["timezone_detected"] is True

    @override_settings(TIME_ZONE="Asia/Tokyo")
    def test_returns_server_timezone(self) -> None:
        context = timezone_context(self.factory.get("/"))

        assert context == {
            "timezone_detected": False,
            "server_timezone": "Asia/Tokyo",
        }
