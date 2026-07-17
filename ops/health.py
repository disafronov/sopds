"""Health check endpoints for Docker HEALTHCHECK."""

import logging

from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)


def check_database() -> tuple[bool, str]:
    """Check database connectivity."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True, "Database connection OK"
    except DatabaseError:
        logger.exception("Database readiness check failed")
        return False, "Database connection failed"


def liveness(_request: HttpRequest) -> JsonResponse:
    """
    Liveness probe checks that the application process is running.
    """
    return JsonResponse({"status": "ok"})


def readiness(_request: HttpRequest) -> JsonResponse:
    """
    Readiness probe checks that the application is ready to accept traffic.

    It verifies availability of critical dependencies.
    """
    checks = {"database": check_database()}

    all_ok = all(status for status, _ in checks.values())

    if not all_ok:
        return JsonResponse(
            {"status": "error", "checks": {k: v[1] for k, v in checks.items()}},
            status=503,
        )

    return JsonResponse(
        {"status": "ok", "checks": {k: v[1] for k, v in checks.items()}}
    )
