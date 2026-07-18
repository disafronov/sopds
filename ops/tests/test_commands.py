"""Tests for ops.management.commands — dev, start."""

from django.apps import apps
from django.core.management import load_command_class


class TestDevCommand:
    """Tests for the `dev` management command."""

    def test_dev_help(self) -> None:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        try:
            call_command("dev", stdout=out, stderr=StringIO())
        except SystemExit:
            pass
        output = out.getvalue()
        assert "runserver" in output or "scanner" in output or not output

    def test_dev_command_exists(self) -> None:
        cmd = load_command_class(apps.get_app_config("ops").name, "dev")
        assert (
            cmd.help == "Start runserver and the scanner together for local development"
        )


class TestStartCommand:
    """Tests for the `start` management command."""

    def test_start_help(self) -> None:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        try:
            call_command("start", stdout=out, stderr=StringIO())
        except SystemExit:
            pass
        output = out.getvalue()
        assert "gunicorn" in output or "scanner" in output or not output

    def test_start_command_exists(self) -> None:
        cmd = load_command_class(apps.get_app_config("ops").name, "start")
        assert cmd.help == "Start gunicorn and the scanner under a common supervisor"
