"""Tests for deployment-critical settings validation."""

import os
import subprocess
import sys


def _import_settings(**environment: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DJANGO_SECRET_KEY"] = "unsafe-secret-key-for-tooling"
    for name, value in environment.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )


def test_database_url_is_required() -> None:
    result = _import_settings(DATABASE_URL=None)

    assert result.returncode != 0
    assert "DATABASE_URL is required" in result.stderr


def test_sqlite_database_url_is_rejected() -> None:
    result = _import_settings(DATABASE_URL="sqlite:////tmp/sopds.sqlite3")

    assert result.returncode != 0
    assert "SQLite is unsupported" in result.stderr


def test_postgresql_database_url_is_accepted() -> None:
    result = _import_settings(
        DATABASE_URL="postgresql://unused:unused@localhost/unused"
    )

    assert result.returncode == 0, result.stderr
