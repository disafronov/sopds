from __future__ import annotations

import functools
import io
import os
from typing import Any, BinaryIO, Callable, cast

from constance import config
from django.conf import settings as django_settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
)
from django.views.decorators.cache import cache_page
from PIL import Image

import opds_catalog.zipf as zipfile
from book_tools.format import create_bookfile, mime_detector
from book_tools.format.mimetype import Mimetype
from opds_catalog import opdsdb, settings, utils
from opds_catalog.models import Book, bookshelf


def getFileName(book: Book) -> str:
    if config.SOPDS_TITLE_AS_FILENAME:
        transname = utils.translit(book.title + "." + book.format)
    else:
        transname = utils.translit(book.filename)

    return utils.to_ascii(transname)


def getFileData(book: Book) -> io.BytesIO:
    full_path = os.path.join(django_settings.SOPDS_ROOT_LIB, book.catalog.path)
    if book.catalog.cat_type == opdsdb.CAT_INP:
        inp_path, zip_name = os.path.split(full_path)
        inpx_path, inp_name = os.path.split(inp_path)
        path, inpx_name = os.path.split(inpx_path)
        full_path = os.path.join(path, zip_name)

    z = None
    fz = None
    fo: BinaryIO | None = None

    if book.catalog.cat_type == opdsdb.CAT_NORMAL:
        file_path = os.path.join(full_path, book.filename)
        try:
            fo = open(file_path, "rb")
        except FileNotFoundError:
            fo = None

    elif book.catalog.cat_type in [opdsdb.CAT_ZIP, opdsdb.CAT_INP]:
        try:
            fz = open(full_path, "rb")
            z = zipfile.ZipFile(fz, "r", allowZip64=True)
            fo = cast(BinaryIO, z.open(book.filename))
        except FileNotFoundError:
            fo = None

    if fo is None:
        raise Http404

    dio = io.BytesIO()
    try:
        dio.write(fo.read())
        dio.seek(0)
    finally:
        fo.close()
        if z:
            z.close()
        if fz:
            fz.close()

    return dio


def getBookAnnotation(book: Book) -> str | None:
    """Extract a book annotation directly from its source file."""
    try:
        book_data = create_bookfile(getFileData(book), book.filename)
        return book_data.description
    except Exception:
        return None


def Annotation(request: HttpRequest, book_id: int) -> HttpResponse:
    """Load one book's annotation from its source file."""
    book = Book.objects.get(id=book_id)
    annotation = getBookAnnotation(book)
    return HttpResponse(annotation or "", content_type="text/html; charset=utf-8")


def getFileDataZip(book: Book) -> io.BytesIO:
    transname = getFileName(book)
    fo = getFileData(book)
    dio = io.BytesIO()
    zo = zipfile.ZipFile(dio, "w", zipfile.ZIP_DEFLATED)
    zo.writestr(transname, fo.read())
    zo.close()
    dio.seek(0)

    return dio


def _add_downloaded_book_to_bookshelf(request: HttpRequest, book: Book) -> None:
    if config.SOPDS_AUTH and request.user.is_authenticated:
        bookshelf.objects.get_or_create(user=request.user, book=book)


def Download(request: HttpRequest, book_id: int, zip_flag: str) -> HttpResponse:
    """Stream a book file to the client without loading it entirely into memory."""
    book = Book.objects.get(id=book_id)

    full_path = os.path.join(django_settings.SOPDS_ROOT_LIB, book.catalog.path)

    if book.catalog.cat_type == opdsdb.CAT_INP:
        inp_path, zip_name = os.path.split(full_path)
        inpx_path, inp_name = os.path.split(inp_path)
        path, inpx_name = os.path.split(inpx_path)
        full_path = os.path.join(path, zip_name)

    if config.SOPDS_TITLE_AS_FILENAME:
        transname = utils.translit(book.title + "." + book.format)
    else:
        transname = utils.translit(book.filename)

    transname = utils.to_ascii(transname)

    if zip_flag == "1":
        dlfilename = transname + ".zip"
        content_type = Mimetype.FB2_ZIP if book.format == "fb2" else Mimetype.ZIP
    else:
        dlfilename = transname
        content_type = mime_detector.fmt(book.format)

    z = None
    fz = None
    fo: BinaryIO | None = None
    book_size = book.filesize

    if book.catalog.cat_type == opdsdb.CAT_NORMAL:
        file_path = os.path.join(full_path, book.filename)
        try:
            book_size = os.path.getsize(file_path)
            fo = open(file_path, "rb")
        except FileNotFoundError:
            raise Http404
    elif book.catalog.cat_type in [opdsdb.CAT_ZIP, opdsdb.CAT_INP]:
        try:
            fz = open(full_path, "rb")
        except FileNotFoundError:
            raise Http404
        z = zipfile.ZipFile(fz, "r", allowZip64=True)
        book_size = z.getinfo(book.filename).file_size
        fo = cast(BinaryIO, z.open(book.filename))
    else:
        raise Http404

    if zip_flag == "1":
        dio = io.BytesIO()
        zo = zipfile.ZipFile(dio, "w", zipfile.ZIP_DEFLATED)
        zo.writestr(transname, fo.read())
        zo.close()
        buf = dio.getvalue()
        response = HttpResponse(buf)
        response["Content-Length"] = str(len(buf))
        # All data is in memory; safe to close handles now.
        if fo:
            fo.close()
        if z:
            z.close()
        if fz:
            fz.close()
    else:
        # FileResponse registers fo.close in _resource_closers and will
        # close the handle after the WSGI handler finishes streaming.
        # django-stubs doesn't recognise FileResponse as HttpResponse.
        response = FileResponse(fo)  # type: ignore[assignment]
        response["Content-Length"] = str(book_size)

    response["Content-Type"] = '%s; name="%s"' % (content_type, dlfilename)
    response["Content-Disposition"] = 'attachment; filename="%s"' % (dlfilename)
    response["Content-Transfer-Encoding"] = "binary"

    _add_downloaded_book_to_bookshelf(request, book)
    return response


def _cache_cover(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    # Defer constance lookup to request time.
    # @cache_page evaluates its timeout argument at import time, which queries
    # the constance_constance table during Django's system check (run by
    # `manage.py migrate` before migrations are applied) and crashes when the
    # table does not yet exist. Wrapping it keeps the timeout lazy.
    @functools.wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        return cache_page(config.SOPDS_CACHE_TIME)(view)(request, *args, **kwargs)

    return wrapper


@_cache_cover
def Cover(request: HttpRequest, book_id: int, thumbnail: bool = False) -> HttpResponse:
    """Загрузка обложки"""
    book = Book.objects.get(id=book_id)
    response = HttpResponse()
    full_path = os.path.join(django_settings.SOPDS_ROOT_LIB, book.catalog.path)
    if book.catalog.cat_type == opdsdb.CAT_INP:
        inp_path, zip_name = os.path.split(full_path)
        inpx_path, inp_name = os.path.split(inp_path)
        path, inpx_name = os.path.split(inpx_path)
        full_path = os.path.join(path, zip_name)

    book_data: Any = None
    image: bytes | None = None
    fo: BinaryIO
    try:
        if book.catalog.cat_type == opdsdb.CAT_NORMAL:
            file_path = os.path.join(full_path, book.filename)
            fo = open(file_path, "rb")
            book_data = create_bookfile(fo, book.filename)
            image = book_data.extract_cover_memory()
            fo.close()
        elif book.catalog.cat_type in [opdsdb.CAT_ZIP, opdsdb.CAT_INP]:
            fz = open(full_path, "rb")
            z = zipfile.ZipFile(fz, "r", allowZip64=True)
            fo = cast(BinaryIO, z.open(book.filename))
            book_data = create_bookfile(fo, book.filename)
            image = book_data.extract_cover_memory()
            fo.close()
            z.close()
            fz.close()
    except Exception:
        book_data = None
        image = None

    if image:
        response["Content-Type"] = "image/jpeg"
        if thumbnail:
            thumb = Image.open(io.BytesIO(image)).convert("RGB")
            thumb.thumbnail(
                (settings.THUMB_SIZE, settings.THUMB_SIZE),
                Image.Resampling.LANCZOS,
            )
            tfile = io.BytesIO()
            thumb.save(tfile, "JPEG")
            image = tfile.getvalue()
        response.write(image)

    if not image:
        nocover_url = staticfiles_storage.url("images/nocover.jpg")
        return HttpResponseRedirect(nocover_url, status=307)

    return response


def Thumbnail(request: HttpRequest, book_id: int) -> HttpResponse:
    return Cover(request, book_id, True)
