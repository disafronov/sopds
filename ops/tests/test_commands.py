"""Tests for ops.management.commands — dev, start."""

from django.apps import apps
from django.core.management import load_command_class


class TestDevCommand:
    """Tests for the `dev` management command."""

    def test_dev_help(self) -> None:
        from io import StringIO

        cmd = load_command_class(apps.get_app_config("ops").name, "dev")
        parser = cmd.create_parser("manage.py", "dev")
        out = StringIO()
        parser.print_help(out)
        output = out.getvalue()
        assert "runserver" in output
        assert "scanner" in output

    def test_dev_command_exists(self) -> None:
        cmd = load_command_class(apps.get_app_config("ops").name, "dev")
        assert (
            cmd.help == "Start runserver and the scanner together for local development"
        )


class TestStartCommand:
    """Tests for the `start` management command."""

    def test_start_help(self) -> None:
        from io import StringIO

        cmd = load_command_class(apps.get_app_config("ops").name, "start")
        parser = cmd.create_parser("manage.py", "start")
        out = StringIO()
        parser.print_help(out)
        output = out.getvalue()
        assert "gunicorn" in output
        assert "scanner" in output

    def test_start_command_exists(self) -> None:
        cmd = load_command_class(apps.get_app_config("ops").name, "start")
        assert cmd.help == "Start gunicorn and the scanner under a common supervisor"
