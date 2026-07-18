"""Tests for ops.health — liveness/readiness probes."""

import json
from typing import Any
from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.test import Client


class TestLiveness:
    """Tests for the liveness probe."""

    def test_liveness_returns_ok(self, db: Any) -> None:
        client = Client()
        response = client.get("/health/liveness/")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data == {"status": "ok"}


class TestReadiness:
    """Tests for the readiness probe (checks database)."""

    def test_readiness_ok(self, db: Any) -> None:
        client = Client()
        response = client.get("/health/readiness/")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "ok"
        assert data["checks"]["database"] == "Database connection OK"

    def test_readiness_db_down(self, db: Any) -> None:
        """When database check fails, readiness returns 503."""
        with patch("ops.health.check_database") as mock_check:
            mock_check.return_value = (False, "Database connection failed")
            client = Client()
            response = client.get("/health/readiness/")
        assert response.status_code == 503
        data = json.loads(response.content)
        assert data["status"] == "error"
        assert data["checks"]["database"] == "Database connection failed"


class TestCheckDatabase:
    """Tests for check_database()."""

    def test_check_database_ok(self, db: Any) -> None:
        from ops.health import check_database

        ok, msg = check_database()
        assert ok is True
        assert msg == "Database connection OK"

    def test_check_database_failure(self) -> None:
        """check_database catches DatabaseError, logs it, and returns failure."""
        from ops.health import check_database

        with (
            patch("ops.health.logger") as mock_logger,
            patch("django.db.connection.cursor") as mock_cursor,
        ):
            mock_cursor.side_effect = DatabaseError("db unavailable")
            ok, msg = check_database()

        assert ok is False
        assert msg == "Database connection failed"
        mock_logger.exception.assert_called_once_with("Database readiness check failed")

    def test_check_database_unexpected_error(self) -> None:
        """An unexpected error (RuntimeError) propagates through check_database()."""
        from ops.health import check_database

        with patch("django.db.connection.cursor") as mock_cursor:
            mock_cursor.side_effect = RuntimeError("unexpected")
            with pytest.raises(RuntimeError, match="unexpected"):
                check_database()
