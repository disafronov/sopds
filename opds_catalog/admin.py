from typing import TYPE_CHECKING

from django.contrib import admin

from opds_catalog.models import Genre

# ``ModelAdmin`` is not runtime-subscriptable in this django-stubs version
# (it is patched for QuerySet/Manager but not for ModelAdmin), yet mypy's
# strict mode requires the generic type parameter. Resolve the base class via
# a TYPE_CHECKING-only alias so the subscript is never evaluated at runtime.
if TYPE_CHECKING:
    _ModelAdminBase = admin.ModelAdmin[Genre]
else:
    _ModelAdminBase = admin.ModelAdmin


# Register your models here.
class Genre_admin(_ModelAdminBase):
    list_display = ("genre", "section", "subsection")


admin.site.register(Genre, Genre_admin)
