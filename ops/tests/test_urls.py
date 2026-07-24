import tomllib
from pathlib import Path

from django.contrib import admin
from django.contrib.admin import AdminSite

from config import urls


def test_admin_index_title_contains_project_name_and_version() -> None:
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text("utf-8")
    )
    project = pyproject["project"]

    assert admin.site.index_title == f"{project['name']} {project['version']}"


def test_project_title_falls_back_when_pyproject_is_missing(tmp_path: Path) -> None:
    default_title = AdminSite().index_title

    assert (
        urls._project_title(tmp_path / "missing.toml", default_title) == default_title
    )
