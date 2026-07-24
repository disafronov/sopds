from __future__ import annotations

import base64
import functools
import io
import os
from typing import Any, BinaryIO, Callable, cast

from constance import config
from django.conf import settings as django_settings
from django.http import Http404, HttpRequest, HttpResponse
from django.views.decorators.cache import cache_page
from PIL import Image

import opds_catalog.zipf as zipfile
from book_tools.format import create_bookfile, mime_detector
from book_tools.format.mimetype import Mimetype
from opds_catalog import fb2parse, opdsdb, settings, utils
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

    dio = io.BytesIO()
    assert fo is not None
    dio.write(fo.read())
    dio.seek(0)

    if fo:
        fo.close()
    if z:
        z.close()
    if fz:
        fz.close()

    return dio


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
    """Загрузка файла книги"""
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

    response = HttpResponse()
    response["Content-Type"] = '%s; name="%s"' % (content_type, dlfilename)
    response["Content-Disposition"] = 'attachment; filename="%s"' % (dlfilename)
    response["Content-Transfer-Encoding"] = "binary"

    z = None
    fz = None
    fo: BinaryIO
    book_size = book.filesize
    if book.catalog.cat_type == opdsdb.CAT_NORMAL:
        file_path = os.path.join(full_path, book.filename)
        book_size = os.path.getsize(file_path)
        try:
            fo = open(file_path, "rb")
        except FileNotFoundError:
            raise Http404
        s: bytes = fo.read()
    elif book.catalog.cat_type in [opdsdb.CAT_ZIP, opdsdb.CAT_INP]:
        try:
            fz = open(full_path, "rb")
        except FileNotFoundError:
            raise Http404
        z = zipfile.ZipFile(fz, "r", allowZip64=True)
        book_size = z.getinfo(book.filename).file_size
        fo = cast(BinaryIO, z.open(book.filename))
        s = fo.read()
    else:
        raise Http404

    if zip_flag == "1":
        dio = io.BytesIO()
        zo = zipfile.ZipFile(dio, "w", zipfile.ZIP_DEFLATED)
        zo.writestr(transname, s)
        zo.close()
        buf = dio.getvalue()
        response["Content-Length"] = str(len(buf))
        response.write(buf)
    else:
        response["Content-Length"] = str(book_size)
        response.write(s)

    fo.close()
    if z:
        z.close()
    if fz:
        fz.close()

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
        if os.path.exists(django_settings.SOPDS_NOCOVER_PATH):
            response["Content-Type"] = "image/jpeg"
            f = open(django_settings.SOPDS_NOCOVER_PATH, "rb")
            response.write(f.read())
            f.close()
        else:
            raise Http404

    return response


def Cover0(request: HttpRequest, book_id: int, thumbnail: bool = False) -> HttpResponse:
    """Загрузка обложки"""
    book = Book.objects.get(id=book_id)
    response = HttpResponse()
    c0 = 0
    full_path = os.path.join(django_settings.SOPDS_ROOT_LIB, book.catalog.path)
    if book.catalog.cat_type == opdsdb.CAT_INP:
        inp_path, zip_name = os.path.split(full_path)
        inpx_path, inp_name = os.path.split(inp_path)
        path, inpx_name = os.path.split(inpx_path)
        full_path = os.path.join(path, zip_name)

    if book.format == "fb2":
        fb2 = fb2parse.fb2parser(1)
        fo: BinaryIO
        if book.catalog.cat_type == opdsdb.CAT_NORMAL:
            file_path = os.path.join(full_path, book.filename)
            fo = open(file_path, "rb")
            fb2.parse(fo, 0)
            fo.close()
        elif book.catalog.cat_type in [opdsdb.CAT_ZIP, opdsdb.CAT_INP]:
            fz = open(full_path, "rb")
            z = zipfile.ZipFile(fz, "r", allowZip64=True)
            fo = cast(BinaryIO, z.open(book.filename))
            fb2.parse(fo, 0)
            fo.close()
            z.close()
            fz.close()

        if len(fb2.cover_image.cover_data) > 0:
            try:
                s = fb2.cover_image.cover_data
                dstr = base64.b64decode(s)
                if thumbnail:
                    response["Content-Type"] = "image/jpeg"
                    thumb = Image.open(io.BytesIO(dstr)).convert("RGB")
                    thumb.thumbnail(
                        (settings.THUMB_SIZE, settings.THUMB_SIZE),
                        Image.Resampling.LANCZOS,
                    )
                    tfile = io.BytesIO()
                    thumb.save(tfile, "JPEG")
                    dstr = tfile.getvalue()
                else:
                    response["Content-Type"] = (
                        fb2.cover_image.getattr("content-type") or "image/jpeg"
                    )
                response.write(dstr)
                c0 = 1
            except Exception:
                c0 = 0

    if c0 == 0:
        if os.path.exists(django_settings.SOPDS_NOCOVER_PATH):
            response["Content-Type"] = "image/jpeg"
            f = open(django_settings.SOPDS_NOCOVER_PATH, "rb")
            response.write(f.read())
            f.close()
        else:
            raise Http404

    return response


def Thumbnail(request: HttpRequest, book_id: int) -> HttpResponse:
    return Cover(request, book_id, True)
