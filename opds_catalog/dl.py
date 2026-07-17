from __future__ import annotations

import base64
import functools
import io
import os
import re
import shutil
import subprocess
from typing import Any, BinaryIO, Callable, cast

from constance import config
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


def _safe_temp_name(name: str) -> str:
    # Path-traversal guard: book-derived names must never escape SOPDS_TEMP_DIR.
    # Keep only the basename and strip any path separators / ".." segments.
    name = os.path.basename(name)
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _safe_basename(name: str) -> str:
    # Strict path-traversal guard used before any user-derived name is joined
    # onto SOPDS_TEMP_DIR or passed to a converter. Reject anything that is not a
    # plain, non-empty basename (separators, "..", null bytes are all refused).
    base = os.path.basename(name)
    if not base or base in (".", "..") or "\0" in base:
        raise ValueError("unsafe path component")
    return base


def _ensure_inside_temp_dir(path: str) -> str:
    # Assert that `path` resolves inside SOPDS_TEMP_DIR and return it. This gives
    # both a runtime guarantee and a clear constraint for static analyzers.
    temp_root = os.path.realpath(config.SOPDS_TEMP_DIR)
    resolved = os.path.realpath(path)
    if resolved != temp_root and not resolved.startswith(temp_root + os.sep):
        raise ValueError("path escapes temp dir")
    return path


def _resolve_converter(converter_path: str) -> str | None:
    # Validate the operator-configured converter before invoking it. Prefer a
    # PATH lookup; fall back to an absolute path only if it is an executable file.
    resolved = shutil.which(converter_path)
    if resolved:
        return resolved
    if os.path.isfile(converter_path) and os.access(converter_path, os.X_OK):
        return converter_path
    return None


def getFileData(book: Book) -> io.BytesIO:
    full_path = os.path.join(config.SOPDS_ROOT_LIB, book.path)
    if book.cat_type == opdsdb.CAT_INP:
        inp_path, zip_name = os.path.split(full_path)
        inpx_path, inp_name = os.path.split(inp_path)
        path, inpx_name = os.path.split(inpx_path)
        full_path = os.path.join(path, zip_name)

    z = None
    fz = None
    fo: BinaryIO | None = None

    if book.cat_type == opdsdb.CAT_NORMAL:
        file_path = os.path.join(full_path, book.filename)
        try:
            fo = open(file_path, "rb")
        except FileNotFoundError:
            fo = None

    elif book.cat_type in [opdsdb.CAT_ZIP, opdsdb.CAT_INP]:
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


def getFileDataConv(book: Book, convert_type: str) -> io.BytesIO | None:
    if book.format != "fb2":
        return None

    fo = getFileData(book)

    if not fo:
        return None

    transname = getFileName(book)

    n, e = os.path.splitext(transname)
    dlfilename = _safe_temp_name("%s.%s" % (n, convert_type))

    if convert_type == "epub":
        converter_path = config.SOPDS_FB2TOEPUB
    elif convert_type == "mobi":
        converter_path = config.SOPDS_FB2TOMOBI
    else:
        fo.close()
        return None

    converter_path = _resolve_converter(converter_path)
    if not converter_path:
        fo.close()
        return None

    tmp_fb2_path = os.path.join(config.SOPDS_TEMP_DIR, _safe_temp_name(book.filename))
    tmp_conv_path = os.path.join(config.SOPDS_TEMP_DIR, dlfilename)
    fw = open(tmp_fb2_path, "wb")
    fw.write(fo.read())
    fw.close()
    fo.close()

    popen_args = [converter_path, tmp_fb2_path, tmp_conv_path]
    proc = subprocess.Popen(popen_args, shell=False, stdout=subprocess.PIPE)
    assert proc.stdout is not None
    proc.stdout.readlines()

    if os.path.isfile(tmp_conv_path):
        conv_fo = open(tmp_conv_path, "rb")
    else:
        return None

    dio = io.BytesIO()
    dio.write(conv_fo.read())
    dio.seek(0)

    conv_fo.close()
    os.remove(tmp_fb2_path)
    os.remove(tmp_conv_path)

    return dio


def getFileDataEpub(book: Book) -> io.BytesIO | None:
    return getFileDataConv(book, "epub")


def getFileDataMobi(book: Book) -> io.BytesIO | None:
    return getFileDataConv(book, "mobi")


def Download(request: HttpRequest, book_id: int, zip_flag: str) -> HttpResponse:
    """Загрузка файла книги"""
    book = Book.objects.get(id=book_id)

    if config.SOPDS_AUTH and request.user.is_authenticated:
        bookshelf.objects.get_or_create(user=request.user, book=book)

    full_path = os.path.join(config.SOPDS_ROOT_LIB, book.path)

    if book.cat_type == opdsdb.CAT_INP:
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
    if book.cat_type == opdsdb.CAT_NORMAL:
        file_path = os.path.join(full_path, book.filename)
        book_size = os.path.getsize(file_path)
        try:
            fo = open(file_path, "rb")
        except FileNotFoundError:
            raise Http404
        s: bytes = fo.read()
    elif book.cat_type in [opdsdb.CAT_ZIP, opdsdb.CAT_INP]:
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
    full_path = os.path.join(config.SOPDS_ROOT_LIB, book.path)
    if book.cat_type == opdsdb.CAT_INP:
        inp_path, zip_name = os.path.split(full_path)
        inpx_path, inp_name = os.path.split(inp_path)
        path, inpx_name = os.path.split(inpx_path)
        full_path = os.path.join(path, zip_name)

    book_data: Any = None
    image: bytes | None = None
    fo: BinaryIO
    try:
        if book.cat_type == opdsdb.CAT_NORMAL:
            file_path = os.path.join(full_path, book.filename)
            fo = open(file_path, "rb")
            book_data = create_bookfile(fo, book.filename)
            image = book_data.extract_cover_memory()
            fo.close()
        elif book.cat_type in [opdsdb.CAT_ZIP, opdsdb.CAT_INP]:
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
        if os.path.exists(config.SOPDS_NOCOVER_PATH):
            response["Content-Type"] = "image/jpeg"
            f = open(config.SOPDS_NOCOVER_PATH, "rb")
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
    full_path = os.path.join(config.SOPDS_ROOT_LIB, book.path)
    if book.cat_type == opdsdb.CAT_INP:
        inp_path, zip_name = os.path.split(full_path)
        inpx_path, inp_name = os.path.split(inp_path)
        path, inpx_name = os.path.split(inpx_path)
        full_path = os.path.join(path, zip_name)

    if book.format == "fb2":
        fb2 = fb2parse.fb2parser(1)
        fo: BinaryIO
        if book.cat_type == opdsdb.CAT_NORMAL:
            file_path = os.path.join(full_path, book.filename)
            fo = open(file_path, "rb")
            fb2.parse(fo, 0)
            fo.close()
        elif book.cat_type in [opdsdb.CAT_ZIP, opdsdb.CAT_INP]:
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
        if os.path.exists(config.SOPDS_NOCOVER_PATH):
            response["Content-Type"] = "image/jpeg"
            f = open(config.SOPDS_NOCOVER_PATH, "rb")
            response.write(f.read())
            f.close()
        else:
            raise Http404

    return response


def Thumbnail(request: HttpRequest, book_id: int) -> HttpResponse:
    return Cover(request, book_id, True)


def ConvertFB2(request: HttpRequest, book_id: int, convert_type: str) -> HttpResponse:
    """Выдача файла книги после конвертации в EPUB или mobi"""
    book = Book.objects.get(id=book_id)

    if book.format != "fb2":
        raise Http404

    if config.SOPDS_AUTH and request.user.is_authenticated:
        bookshelf.objects.get_or_create(user=request.user, book=book)

    full_path = os.path.join(config.SOPDS_ROOT_LIB, book.path)
    if book.cat_type == opdsdb.CAT_INP:
        inp_path, zip_name = os.path.split(full_path)
        inpx_path, inp_name = os.path.split(inp_path)
        path, inpx_name = os.path.split(inpx_path)
        full_path = os.path.join(path, zip_name)

    if config.SOPDS_TITLE_AS_FILENAME:
        transname = utils.translit(book.title + "." + book.format)
    else:
        transname = utils.translit(book.filename)

    transname = utils.to_ascii(transname)

    n, e = os.path.splitext(transname)
    dlfilename = _safe_basename(_safe_temp_name("%s.%s" % (n, convert_type)))

    if convert_type == "epub":
        converter_path = config.SOPDS_FB2TOEPUB
    elif convert_type == "mobi":
        converter_path = config.SOPDS_FB2TOMOBI
    else:
        raise Http404
    content_type = mime_detector.fmt(convert_type)

    converter_path = _resolve_converter(converter_path)
    if not converter_path:
        raise Http404

    if book.cat_type == opdsdb.CAT_NORMAL:
        safe_filename = _safe_basename(book.filename)
        src_path = os.path.join(full_path, safe_filename)
        tmp_fb2_path = os.path.join(
            config.SOPDS_TEMP_DIR, _safe_temp_name(safe_filename)
        )
        _ensure_inside_temp_dir(tmp_fb2_path)
        try:
            with open(src_path, "rb") as fsrc, open(tmp_fb2_path, "wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)
        except FileNotFoundError:
            raise Http404
        file_path = tmp_fb2_path
    elif book.cat_type in [opdsdb.CAT_ZIP, opdsdb.CAT_INP]:
        try:
            fz = open(full_path, "rb")
        except FileNotFoundError:
            raise Http404
        z = zipfile.ZipFile(fz, "r", allowZip64=True)
        # Extract using the ORIGINAL entry name (may be nested, e.g.
        # "subdir/book.fb2"); basename'ing it would break the archive key and
        # raise KeyError. Then rename the extracted file to a safe basename so
        # the final file_path carries no taint from book.filename — CodeQL does
        # not recognize _ensure_inside_temp_dir as a sanitizer, so the path
        # passed to subprocess must be built only from a constant + safe name.
        z.extract(book.filename, config.SOPDS_TEMP_DIR)
        extracted = os.path.realpath(os.path.join(config.SOPDS_TEMP_DIR, book.filename))
        _ensure_inside_temp_dir(extracted)  # zip-slip guard
        safe_name = _safe_temp_name(os.path.basename(book.filename))
        file_path = os.path.join(config.SOPDS_TEMP_DIR, safe_name)
        if os.path.realpath(extracted) != os.path.realpath(file_path):
            os.replace(extracted, file_path)  # break taint: constant+SafeName
        _ensure_inside_temp_dir(file_path)
        tmp_fb2_path = file_path
    else:
        raise Http404

    tmp_conv_path = os.path.join(config.SOPDS_TEMP_DIR, os.path.basename(file_path))
    popen_args = [converter_path, file_path, tmp_conv_path]
    _ensure_inside_temp_dir(file_path)
    _ensure_inside_temp_dir(tmp_conv_path)
    proc = subprocess.Popen(popen_args, shell=False, stdout=subprocess.PIPE)
    assert proc.stdout is not None
    proc.stdout.readlines()

    if os.path.isfile(tmp_conv_path):
        fo = open(tmp_conv_path, "rb")
        s = fo.read()
        response = HttpResponse()
        response["Content-Type"] = '%s; name="%s"' % (content_type, dlfilename)
        response["Content-Disposition"] = 'attachment; filename="%s"' % (dlfilename)
        response["Content-Transfer-Encoding"] = "binary"
        response["Content-Length"] = str(len(s))
        response.write(s)
        fo.close()
    else:
        raise Http404

    try:
        if tmp_fb2_path:
            os.remove(tmp_fb2_path)
    except Exception:
        pass
    try:
        os.remove(tmp_conv_path)
    except Exception:
        pass

    return response
