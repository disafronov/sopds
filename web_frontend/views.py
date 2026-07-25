from random import randint
from typing import Any, cast

from constance import config
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models.functions import Upper
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.template.context_processors import csrf
from django.urls import reverse, reverse_lazy
from django.utils.html import strip_tags
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from opds_catalog import models, settings
from opds_catalog.models import (
    Author,
    Book,
    Counter,
    Genre,
    Series,
    bookshelf,
    lang_menu,
)
from opds_catalog.opds_paginator import Paginator as OPDS_Paginator
from web_frontend.settings import HALF_PAGES_LINKS, LOGIN_NEXT_SESSION_KEY


def sopds_processor(request: HttpRequest) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["app_title"] = settings.TITLE
    args["sopds_auth"] = config.SOPDS_AUTH
    args["alphabet"] = config.SOPDS_ALPHABET_MENU
    args["splititems"] = config.SOPDS_SPLITITEMS
    args["nozip"] = settings.NOZIP_FORMATS
    args["cache_t"] = 0

    if config.SOPDS_ALPHABET_MENU:
        args["lang_menu"] = lang_menu

    if config.SOPDS_AUTH:
        user = request.user
        if user.is_authenticated:
            latest_bookshelf_entry = (
                bookshelf.objects.filter(user=user)
                .select_related("book")
                .prefetch_related(
                    "book__authors", "book__genres", "book__bseries_set__ser"
                )
                .order_by("-readtime")
                .first()
            )
            args["last_bookshelf_book"] = (
                _footer_book_data(latest_bookshelf_entry.book)
                if latest_bookshelf_entry
                else None
            )

    books_count = Counter.objects.get_counter(models.counter_allbooks)
    if books_count:
        random_id = randint(1, books_count)
        try:
            random_book = Book.objects.prefetch_related(
                "authors", "genres", "bseries_set__ser"
            ).all()[random_id - 1 : random_id][0]
        except Book.DoesNotExist:
            random_book = None
    else:
        random_book = None

    args["random_book"] = _footer_book_data(random_book) if random_book else None
    stats: dict[str, Any] = {d["name"]: d["value"] for d in Counter.obj.all().values()}
    stats["lastscan_date"] = Counter.objects.get_lastscan()
    args["stats"] = stats

    return args


def _footer_book_data(book: Book) -> dict[str, Any]:
    """Prepare book metadata shared by the two footer cards."""

    return {
        "id": book.id,
        "title": book.title,
        "docdate": book.docdate,
        "filesize": book.filesize // 1000,
        "authors": book.authors.all(),
        "genres": book.genres.all(),
        "series": book.bseries_set.all(),
    }


# Create your views here.
@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
def SearchBooksView(request: HttpRequest) -> HttpResponse:
    # Read searchtype, searchterms, searchterms0, page from form
    args: dict[str, Any] = {}
    args.update(csrf(request))

    if request.GET:
        searchtype = request.GET.get("searchtype", "m")
        searchterms = request.GET.get("searchterms", "")
        if searchtype == "u":
            searchterms = "0"
        if searchtype in {"m", "a", "s", "u"} and searchterms:
            page_num = max(int(request.GET.get("page", "1")), 1)
            feed_kwargs: dict[str, Any] = {
                "searchtype": searchtype,
                "searchterms": searchterms,
            }
            if page_num > 1:
                feed_kwargs["page"] = page_num
            labels = {
                "m": (_("Search by title"), "title"),
                "a": (_("Search by author"), "author"),
                "s": (_("Search by series"), "series"),
                "u": (_("Bookshelf"), "title"),
            }
            label, searchobject = labels.get(searchtype, (_("Search"), "title"))
            breadcrumbs = (
                [_("Books"), label]
                if searchtype == "u"
                else [_("Books"), label, searchterms]
            )
            args.update(
                {
                    "breadcrumbs": breadcrumbs,
                    "searchobject": searchobject,
                    "searchterms": searchterms,
                    "searchterms0": request.GET.get("searchterms0", ""),
                    "searchtype": searchtype,
                    "current": "search",
                    "cache_t": 0,
                    "opds_adapter": {
                        "feed_url": reverse(
                            "opds_catalog:searchbooks", kwargs=feed_kwargs
                        ),
                        "page_url": reverse("web:searchbooks"),
                        "searchtype": searchtype,
                        "searchterms": searchterms,
                        "searchterms0": request.GET.get("searchterms0", ""),
                        "half_pages": HALF_PAGES_LINKS,
                        "isbookshelf": searchtype == "u",
                    },
                }
            )
            if searchtype == "u":
                args["isbookshelf"] = True
            return render(request, "sopds_books_opds.html", args)

    cache_scope = ""
    cache_time = config.SOPDS_CACHE_TIME

    if request.GET:
        searchtype = request.GET.get("searchtype", "m")
        searchterms = request.GET.get("searchterms", "")
        # searchterms0 = int(request.POST.get('searchterms0', ''))
        page_num = int(request.GET.get("page", "1"))
        page_num = page_num if page_num > 0 else 1

        # if (len(searchterms)<3) and (searchtype in ('m', 'b', 'e')):
        #    args['errormsg'] = 'Too few symbols in search string !';
        #    return render_to_response('sopds_error.html', args)

        books = Book.objects.none()

        if searchtype == "m":
            # books = Book.objects.extra(where=["upper(title) like %s"],
            #     params=["%%%s%%"%searchterms.upper()]).order_by('title','-docdate')
            books = Book.objects.filter(
                title__upper__contains=searchterms.upper()
            ).order_by(Upper("title"), "-docdate")
            args["breadcrumbs"] = [_("Books"), _("Search by title"), searchterms]
            args["searchobject"] = "title"

        if searchtype == "b":
            # books = Book.objects.extra(
            #     where=["upper(title) like %s"],
            #     params=["%s%%"%searchterms.upper()]).order_by('title','-docdate')
            books = Book.objects.filter(
                title__upper__startswith=searchterms.upper()
            ).order_by(Upper("title"), "-docdate")
            args["breadcrumbs"] = [_("Books"), _("Search by title"), searchterms]
            args["searchobject"] = "title"

        elif searchtype == "a":
            try:
                author_id = int(searchterms)
                author = Author.objects.get(id=author_id)
                # aname = "%s %s"%(author.last_name,author.first_name)
                aname = author.full_name
            except Exception:
                author_id = 0
                aname = ""
            books = Book.objects.filter(authors=author_id).order_by(
                Upper("title"), "-docdate"
            )
            args["breadcrumbs"] = [_("Books"), _("Search by author"), aname]
            args["searchobject"] = "author"

        # Поиск книг по серии
        elif searchtype == "s":
            try:
                ser_id = int(searchterms)
                ser = Series.objects.get(id=ser_id).ser
            except Exception:
                ser_id = 0
                ser = ""
            books = Book.objects.filter(series=ser_id).order_by(
                "bseries__ser_no", Upper("title"), "-docdate"
            )
            args["breadcrumbs"] = [_("Books"), _("Search by series"), ser]
            args["searchobject"] = "series"

        # Поиск книг по жанру
        elif searchtype == "g":
            try:
                genre_id = int(searchterms)
                section = Genre.objects.get(id=genre_id).section
                subsection = Genre.objects.get(id=genre_id).subsection
                args["breadcrumbs"] = [
                    _("Books"),
                    _("Search by genre"),
                    section,
                    subsection,
                ]
            except Exception:
                genre_id = 0
                args["breadcrumbs"] = [_("Books"), _("Search by genre")]

            books = Book.objects.filter(genres=genre_id).order_by(
                Upper("title"), "-docdate"
            )
            args["searchobject"] = "genre"

        # Поиск книг на книжной полке
        elif searchtype == "u":
            if config.SOPDS_AUTH:
                assert request.user.is_authenticated
                cache_scope = "uncached:%s:" % request.user.pk
                cache_time = 0
                books = Book.objects.filter(bookshelf__user=request.user).order_by(
                    "-bookshelf__readtime"
                )
                args["breadcrumbs"] = [
                    _("Books"),
                    _("Bookshelf"),
                    request.user.username,
                ]
                # books = bookshelf.objects.filter(user=request.user)
                #     .select_related('book')
            else:
                books = Book.objects.filter(id=0)
                args["breadcrumbs"] = [_("Books"), _("Bookshelf")]
            args["searchobject"] = "title"
            args["isbookshelf"] = 1

        # Поиск дубликатов для книги
        elif searchtype == "d":
            # try:
            book_id = int(searchterms)
            mbook = Book.objects.get(id=book_id)
            books = (
                Book.objects.filter(title=mbook.title, authors__in=mbook.authors.all())
                .exclude(id=book_id)
                .distinct()
                .order_by("-docdate")
            )
            args["breadcrumbs"] = [_("Books"), _("Doubles for book"), mbook.title]
            args["searchobject"] = "title"

        # Поиск книги по ID. Хотел найти еще и дубликаты к книге,
        # но почему-то не работает запрос правильно. Ума не приложу почему.
        elif searchtype == "i":
            try:
                book_id = int(searchterms)
                # mbook = Book.objects.get(id=book_id)
            except Exception:
                book_id = 0
                # mbook = None
            books = Book.objects.filter(id=book_id)
            args["breadcrumbs"] = [_("Books"), books[0].title]
            # books = Book.objects.filter(
            #     title=mbook.title, authors__in=mbook.authors.all()
            # ).distinct().order_by('-docdate')
            # args['breadcrumbs'] = [_('Books'),mbook.title]
            args["searchobject"] = "title"

        # if len(books)>0:
        #    books = books.select_related('authors','genres','series')

        # Добавляем Left Join с таблицей BookShelfб чтобы вытащить дату
        # прочтения книги из книжной полки
        # books = books.filter(
        #     Q(bookshelf__isnull=True)|Q(bookshelf__user=request.user))
        # books = books.prefetch_related('bookshelf_set')
        # print(books.query)

        # Фильтруем дубликаты и формируем выдачу затребованной страницы
        books_count = books.count()
        op = OPDS_Paginator(
            books_count, 0, page_num, config.SOPDS_MAXITEMS, HALF_PAGES_LINKS
        )
        items: list[Any] = []

        prev_title = ""
        prev_authors_set: set[Any] = set()

        # Начаинам анализ с последнего элемента на предидущей странице,
        # чторбы он "вытянул" с этой страницы
        # свои дубликаты если они есть
        summary_DOUBLES_HIDE = config.SOPDS_DOUBLES_HIDE and (searchtype != "d")
        start = (
            op.d1_first_pos
            if ((op.d1_first_pos == 0) or (not summary_DOUBLES_HIDE))
            else op.d1_first_pos - 1
        )
        finish = op.d1_last_pos

        for row in books[start : finish + 1]:
            p: dict[str, Any] = {
                "doubles": 0,
                "lang_code": row.lang_code,
                "filename": row.filename,
                "path": row.catalog.path,
                "registerdate": row.registerdate,
                "id": row.id,
                "annotation": strip_tags(row.annotation),
                "docdate": row.docdate,
                "format": row.format,
                "title": row.title,
                "filesize": row.filesize // 1000,
                "authors": row.authors.values(),
                "genres": row.genres.values(),
                "series": row.series.values(),
                "ser_no": row.bseries_set.values("ser_no"),
                "readtime": (
                    row.bookshelf_set.filter(user=cast(User, request.user)).values(
                        "readtime"
                    )
                    if config.SOPDS_AUTH
                    else None
                ),
            }
            if summary_DOUBLES_HIDE:
                title = p["title"]
                authors_set = {a["id"] for a in p["authors"]}
                if (
                    title.upper() == prev_title.upper()
                    and authors_set == prev_authors_set
                ):
                    items[-1]["doubles"] += 1
                else:
                    items.append(p)
                prev_title = title
                prev_authors_set = authors_set
            else:
                items.append(p)

        # "вытягиваем" дубликаты книг со следующей страницы и удаляем первый
        # элемент который с предыдущей страницы и "вытягивал" дубликаты с текущей
        if summary_DOUBLES_HIDE:
            double_flag = True
            while ((finish + 1) < books_count) and double_flag:
                finish += 1
                if (
                    books[finish].title.upper() == prev_title.upper()
                    and {a["id"] for a in books[finish].authors.values()}
                    == prev_authors_set
                ):
                    items[-1]["doubles"] += 1
                else:
                    double_flag = False

            if op.d1_first_pos != 0:
                items.pop(0)

        args["paginator"] = op.get_data_dict()
        args["searchterms"] = searchterms
        args["searchtype"] = searchtype
        args["books"] = items
        args["current"] = "search"
        args["cache_id"] = "%s%s:%s:%s" % (
            cache_scope,
            searchterms,
            searchtype,
            op.page_num,
        )
        args["cache_t"] = cache_time

    return render(request, "sopds_books.html", args)


@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
def SearchSeriesView(request: HttpRequest) -> HttpResponse:
    args = _search_entities_context(
        request,
        entity="series",
        title=_("Series"),
        opds_route="searchseries",
    )
    return render(request, "sopds_series.html", args)


@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
def SearchAuthorsView(request: HttpRequest) -> HttpResponse:
    args = _search_entities_context(
        request,
        entity="author",
        title=_("Authors"),
        opds_route="searchauthors",
    )
    return render(request, "sopds_authors.html", args)


def _search_entities_context(
    request: HttpRequest,
    *,
    entity: str,
    title: str,
    opds_route: str,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args.update(csrf(request))
    if not request.GET:
        return args

    searchtype = request.GET.get("searchtype", "m")
    searchterms = request.GET.get("searchterms", "")
    page_num = max(int(request.GET.get("page", "1")), 1)
    args.update(
        {
            "searchterms": searchterms,
            "searchtype": searchtype,
            "searchobject": entity,
            "current": "search",
            "breadcrumbs": [title, _("Search"), searchterms],
            "cache_id": f"{searchterms}:{searchtype}:{page_num}",
            "cache_t": config.SOPDS_CACHE_TIME,
        }
    )
    if not searchterms:
        return args

    kwargs: dict[str, Any] = {
        "searchtype": searchtype,
        "searchterms": searchterms,
    }
    if page_num > 1:
        kwargs["page"] = page_num

    args.update(
        {
            "opds_adapter": {
                "feed_url": reverse(f"opds_catalog:{opds_route}", kwargs=kwargs),
                "mode": "entity",
                "entity": entity,
                "count_label": _("Total: %(count)s books."),
                "search_url": reverse("web:searchbooks"),
                "page_url": reverse(f"web:{opds_route}"),
                "searchtype": searchtype,
                "searchterms": searchterms,
                "half_pages": HALF_PAGES_LINKS,
            },
        }
    )
    return args


@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
def CatalogsView(request: HttpRequest) -> HttpResponse:
    args: dict[str, Any] = {}

    cat_id = request.GET.get("cat") if request.GET else None
    page_num = max(int(request.GET.get("page", "1")), 1) if request.GET else 1
    feed_kwargs: dict[str, Any] = {}
    if cat_id:
        feed_kwargs["cat_id"] = int(cat_id)
    if cat_id and page_num > 1:
        feed_kwargs["page"] = page_num
    args.update(
        {
            "breadcrumbs": [_("Catalogs")],
            "breadcrumbs_cat": [],
            "current": "catalog",
            "cat_id": cat_id,
            "opds_adapter": {
                "feed_url": reverse(
                    (
                        "opds_catalog:cat_page"
                        if cat_id and page_num > 1
                        else (
                            "opds_catalog:cat_tree"
                            if cat_id
                            else "opds_catalog:catalogs"
                        )
                    ),
                    kwargs=feed_kwargs,
                ),
                "page_url": reverse("web:catalog"),
                "cat_id": cat_id or "",
                "half_pages": HALF_PAGES_LINKS,
            },
        }
    )
    return render(request, "sopds_catalogs_opds.html", args)


def _selector_context(
    request: HttpRequest,
    *,
    current: str,
    count_label: str,
    title: str,
    opds_route: str,
) -> dict[str, Any]:
    """Map a legacy web selector URL to its public OPDS feed."""

    lang_code = int(request.GET.get("lang", "0"))
    chars = request.GET.get("chars", "").upper()
    route = f"opds_catalog:{'chars_' if chars else 'char_'}{opds_route}"
    kwargs: dict[str, Any] = {"lang_code": lang_code}
    if chars:
        kwargs["chars"] = chars

    return {
        "current": current,
        "lang_code": lang_code,
        "breadcrumbs": [title, _("Select"), lang_menu[lang_code], chars],
        "cache_id": f"{current}:{lang_code}:{chars}",
        "cache_t": config.SOPDS_CACHE_TIME,
        "opds_adapter": {
            "feed_url": reverse(route, kwargs=kwargs),
            "feed_kind": opds_route,
            "kind": current,
            "lang_code": lang_code,
            "count_label": count_label,
            "selector_url": reverse(f"web:{current}"),
            "search_url": reverse(f"web:search{opds_route}"),
        },
    }


@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
def BooksView(request: HttpRequest) -> HttpResponse:
    args = _selector_context(
        request,
        current="book",
        count_label=_("Total: %(count)s books."),
        title=_("Books"),
        opds_route="books",
    )
    return render(request, "sopds_selectbook.html", args)


@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
def AuthorsView(request: HttpRequest) -> HttpResponse:
    args = _selector_context(
        request,
        current="author",
        count_label=_("Total: %(count)s authors."),
        title=_("Authors"),
        opds_route="authors",
    )
    return render(request, "sopds_selectauthor.html", args)


@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
def SeriesView(request: HttpRequest) -> HttpResponse:
    args = _selector_context(
        request,
        current="series",
        count_label=_("Total: %(count)s series."),
        title=_("Series"),
        opds_route="series",
    )
    return render(request, "sopds_selectseries.html", args)


@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
def GenresView(request: HttpRequest) -> HttpResponse:
    section_id = int(request.GET.get("section", "0"))
    opds_kwargs = {"section": section_id} if section_id else {}
    args: dict[str, Any] = {
        "breadcrumbs": [_("Genres"), _("Select")],
        "current": "genre",
        "parent_id": section_id,
        "cache_id": f"genre:{section_id}",
        "cache_t": config.SOPDS_CACHE_TIME,
        "opds_adapter": {
            "feed_url": reverse("opds_catalog:genres", kwargs=opds_kwargs),
            "mode": "genre",
            "count_label": _("Total: %(count)s books."),
            "selector_url": reverse("web:genre"),
            "search_url": reverse("web:searchbooks"),
        },
    }

    return render(request, "sopds_selectgenres.html", args)


@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
@login_required(login_url=reverse_lazy("web:login"))
@require_POST
def BSDelView(request: HttpRequest) -> HttpResponse:
    try:
        book_id = int(request.POST["book"])
    except (KeyError, ValueError):
        return HttpResponseBadRequest()

    bookshelf.objects.filter(user=cast(User, request.user), book_id=book_id).delete()

    return _redirect_to_bookshelf()


@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
@login_required(login_url=reverse_lazy("web:login"))
@require_POST
def BSClearView(request: HttpRequest) -> HttpResponse:
    bookshelf.objects.filter(user=cast(User, request.user)).delete()
    return _redirect_to_bookshelf()


def _redirect_to_bookshelf() -> HttpResponse:
    return redirect("%s?searchtype=u" % reverse("web:searchbooks"))


def hello(request: HttpRequest) -> HttpResponse:
    args: dict[str, Any] = {}
    args["breadcrumbs"] = [_("HOME")]
    return render(request, "sopds_hello.html", args)


def LoginView(request: HttpRequest) -> HttpResponse:
    args: dict[str, Any] = {}
    args["breadcrumbs"] = [_("Login")]
    args.update(csrf(request))
    try:
        username = request.POST["username"]
        password = request.POST["password"]
    except KeyError:
        return render(request, "sopds_login.html", args)

    user = authenticate(username=username, password=password)
    if user is not None:
        if user.is_active:
            login(request, user)
            next_url = request.session.pop(LOGIN_NEXT_SESSION_KEY, None)
            if next_url is not None:
                return redirect(next_url)
            return redirect("web:main")
        else:
            args["system_message"] = {
                "text": _("This account is not active!"),
                "type": "alert",
            }
            return handler403(request, args)
            # return render(request, 'sopds_login.html', args)
    else:
        args["system_message"] = {
            "text": _("User does not exist or the password is incorrect!"),
            "type": "alert",
        }
        return handler403(request, args)
        # return render(request, 'sopds_login.html', args)


@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
def LogoutView(request: HttpRequest) -> HttpResponse:
    logout(request)
    args: dict[str, Any] = {}
    args["breadcrumbs"] = [_("Logout")]
    return redirect(reverse("web:main"))


def handler403(request: HttpRequest, args: dict[str, Any]) -> HttpResponse:
    response = render(request, "sopds_login.html", args)
    response.status_code = 403
    return response
