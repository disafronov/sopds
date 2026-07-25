from random import randint
from typing import Any, cast

from constance import config
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.template.context_processors import csrf
from django.urls import reverse, reverse_lazy
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
    """Pass only the book ID; the browser loads metadata through OPDS."""

    return {"id": book.id}


# Create your views here.
@vary_on_headers("HTTP_ACCEPT_LANGUAGE")
def SearchBooksView(request: HttpRequest) -> HttpResponse:
    # Read searchtype, searchterms, searchterms0, page from form
    args: dict[str, Any] = {}
    args.update(csrf(request))

    if request.GET:
        searchtype = request.GET.get("searchtype", "m")
        searchterms = " ".join(request.GET.get("searchterms", "").split())
        display_searchterms = searchterms
        if searchtype in {"a", "s", "g"} and searchterms and not searchterms.isdigit():
            normalized_searchterms = " ".join(searchterms.split())
            model: Any
            model, field = {
                "a": (Author, "full_name"),
                "s": (Series, "ser"),
                "g": (Genre, "subsection"),
            }[searchtype]
            match = model.objects.filter(
                **{f"{field}__iexact": normalized_searchterms}
            ).first()
            if match is None:
                candidates = model.objects.filter(
                    **{f"{field}__icontains": normalized_searchterms}
                )[:20]
                match = next(
                    (
                        candidate
                        for candidate in candidates
                        if " ".join(getattr(candidate, field).split()).casefold()
                        == normalized_searchterms.casefold()
                    ),
                    None,
                )
            if match:
                searchterms = str(match.id)
        if searchtype == "u":
            searchterms = "0"
        if (
            searchtype in {"b", "m", "e", "a", "s", "as", "g", "u", "d", "i"}
            and searchterms
        ):
            page_num = max(int(request.GET.get("page", "1")), 1)
            feed_kwargs: dict[str, Any] = {
                "searchtype": searchtype,
                "searchterms": searchterms,
            }
            if page_num > 1:
                feed_kwargs["page"] = page_num
            if searchtype == "as" and request.GET.get("searchterms0"):
                feed_kwargs["searchterms0"] = request.GET["searchterms0"]
            labels = {
                "b": (_("Search by title"), "title"),
                "m": (_("Search by title"), "title"),
                "e": (_("Search by title"), "title"),
                "a": (_("Search by author"), "author"),
                "s": (_("Search by series"), "series"),
                "as": (_("Search by author and series"), "series"),
                "g": (_("Search by genre"), "genre"),
                "u": (_("Bookshelf"), "title"),
                "d": (_("Doubles for book"), "title"),
                "i": (_("Book"), "title"),
            }
            label, searchobject = labels.get(searchtype, (_("Search"), "title"))
            breadcrumbs = (
                [_("Books"), label]
                if searchtype == "u"
                else [_("Books"), label, display_searchterms]
            )
            args.update(
                {
                    "breadcrumbs": breadcrumbs,
                    "searchobject": searchobject,
                    "searchterms": display_searchterms,
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
                        "searchterms": display_searchterms,
                        "searchterms0": request.GET.get("searchterms0", ""),
                        "half_pages": HALF_PAGES_LINKS,
                        "isbookshelf": searchtype == "u",
                    },
                }
            )
            if searchtype == "u":
                args["isbookshelf"] = True
            return render(request, "sopds_books_opds.html", args)

    # Keep the books page an OPDS client even before a search is selected.
    args.update(
        {
            "breadcrumbs": [_("Books")],
            "searchobject": "title",
            "searchterms": "",
            "searchterms0": "",
            "searchtype": "m",
            "current": "search",
            "cache_t": 0,
            "opds_adapter": {
                "feed_url": reverse("opds_catalog:nolang_books"),
                "page_url": reverse("web:searchbooks"),
                "searchtype": "m",
                "searchterms": "",
                "searchterms0": "",
                "half_pages": HALF_PAGES_LINKS,
                "isbookshelf": False,
            },
        }
    )
    if not request.GET:
        return render(request, "sopds_books_opds.html", args)

    return render(request, "sopds_books_opds.html", args)


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
