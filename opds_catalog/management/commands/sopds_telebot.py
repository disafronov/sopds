from __future__ import annotations

import logging
import re
import sys
from typing import Any, Awaitable, Callable, TypeVar

from constance import config
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import connection, connections
from django.db.models import Q, QuerySet
from django.utils import translation
from django.utils.html import strip_tags
from django.utils.translation import gettext as _
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import InvalidToken
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.update import Update

from opds_catalog import dl, settings
from opds_catalog.models import Book
from opds_catalog.opds_paginator import Paginator as OPDS_Paginator
from sopds_web_backend.settings import HALF_PAGES_LINKS

query_delimiter = "####"

T = TypeVar("T")
Handler = Callable[[Any, Update, ContextTypes.DEFAULT_TYPE], Awaitable[T]]


def cmdtrans(
    func: Handler[T],
) -> Callable[[Any, Update, ContextTypes.DEFAULT_TYPE], Awaitable[T | None]]:
    """Activate the configured UI language for the duration of a handler."""

    async def wrapper(
        self: Any, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> T | None:
        translation.activate(config.SOPDS_LANGUAGE)
        try:
            return await func(self, update, context)
        finally:
            translation.deactivate()

    return wrapper


def CheckAuthDecorator(
    func: Handler[T],
) -> Callable[[Any, Update, ContextTypes.DEFAULT_TYPE], Awaitable[T | None]]:
    """Deny access to users not present (and active) in the Django auth DB."""

    async def wrapper(
        self: Any, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> T | None:
        if not config.SOPDS_TELEBOT_AUTH:
            return await func(self, update, context)

        if connection.connection and not connection.is_usable():
            # Access the private per-connection cache to drop a dead connection.
            del connections._connections.default  # type: ignore[attr-defined]

        if update.message:
            query = update.message
            username = update.message.from_user.username
        else:
            query = update.callback_query.message
            username = update.callback_query.from_user.username

        users = User.objects.filter(username__iexact=username)

        if users and users[0].is_active:
            return await func(self, update, context)

        await context.bot.send_message(
            chat_id=query.chat_id,
            text=_(
                "Hello %s!\n"
                "Unfortunately you do not have access to information. "
                "Please contact the bot administrator."
            )
            % username,
        )
        self.logger.info(_("Denied access for user: %s") % username)
        return None

    return wrapper


class Command(BaseCommand):
    help = "SimpleOPDS Telegram Bot engine."
    can_import_settings = True
    leave_locale_alone = True
    logger: logging.Logger = logging.getLogger("")

    def add_arguments(self, parser: Any) -> None:
        subparsers = parser.add_subparsers(dest="command")
        subparsers.add_parser("start", help="Run the Telegram bot in the foreground.")
        parser.add_argument(
            "--verbose",
            action="store_true",
            dest="verbose",
            default=False,
            help="Set verbosity level for SimpleOPDS telebot.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        self.logger = logging.getLogger("")
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")

        if settings.LOGLEVEL != logging.NOTSET:
            fh = logging.FileHandler(config.SOPDS_TELEBOT_LOG)
            fh.setLevel(settings.LOGLEVEL)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

        if options["verbose"]:
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

        action = options.get("command") or "start"
        if action == "start":
            self.start()
        else:
            self.stdout.write("Unknown command. Use 'start'.")
            return

    @cmdtrans
    @CheckAuthDecorator
    async def startCommand(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await update.message.reply_text(
            _(
                "%(subtitle)s\nHello %(username)s! To search for a book, "
                "enter part of her title or author:"
            )
            % {
                "subtitle": settings.SUBTITLE,
                "username": update.message.from_user.username,
            }
        )
        self.logger.info("Start talking with user: %s" % update.message.from_user)
        return

    def BookFilter(self, query: str) -> QuerySet[Book]:
        if connection.connection and not connection.is_usable():
            # Access the private per-connection cache to drop a dead connection.
            del connections._connections.default  # type: ignore[attr-defined]

        q_objects = Q()
        q_objects.add(Q(search_title__contains=query.upper()), Q.OR)
        q_objects.add(Q(authors__search_full_name__contains=query.upper()), Q.OR)
        books = (
            Book.objects.filter(q_objects)
            .order_by("search_title", "-docdate")
            .distinct()
        )

        return books

    def BookPager(
        self, books: QuerySet[Book], page_num: int, query: str
    ) -> dict[str, Any]:
        books_count = books.count()
        op = OPDS_Paginator(
            books_count, 0, page_num, config.SOPDS_TELEBOT_MAXITEMS, HALF_PAGES_LINKS
        )
        items: list[dict[str, Any]] = []

        prev_title = ""
        prev_authors_set: set[int] = set()

        # Start the analysis from the last element on the previous page, so it
        # can pull its duplicates (if any) from this page.
        summary_DOUBLES_HIDE = config.SOPDS_DOUBLES_HIDE
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
                "path": row.path,
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
            }
            if summary_DOUBLES_HIDE:
                title: Any = p["title"]
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

        # Pull duplicates from the next page and drop the first element which was
        # only kept to pull duplicates from the current page.
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

        response = ""
        for b in items:
            authors = ", ".join([a["full_name"] for a in b["authors"]])
            doubles = _("(doubles:%s) ") % b["doubles"] if b["doubles"] else ""
            response += "<b>%(title)s</b>\n%(author)s\n%(dbl)s/download%(link)s\n\n" % {
                "title": b["title"],
                "author": authors,
                "link": b["id"],
                "dbl": doubles,
            }

        buttons = [
            InlineKeyboardButton(
                "1 <<", callback_data="%s%s%s" % (query, query_delimiter, 1)
            ),
            InlineKeyboardButton(
                "%s <" % op.previous_page_number,
                callback_data="%s%s%s"
                % (query, query_delimiter, op.previous_page_number),
            ),
            InlineKeyboardButton(
                "[ %s ]" % op.number,
                callback_data="%s%s%s" % (query, query_delimiter, "current"),
            ),
            InlineKeyboardButton(
                "> %s" % op.next_page_number,
                callback_data="%s%s%s" % (query, query_delimiter, op.next_page_number),
            ),
            InlineKeyboardButton(
                ">> %s" % op.num_pages,
                callback_data="%s%s%s" % (query, query_delimiter, op.num_pages),
            ),
        ]

        markup = InlineKeyboardMarkup([buttons]) if op.num_pages > 1 else None

        return {"message": response, "buttons": markup}

    @cmdtrans
    @CheckAuthDecorator
    async def getBooks(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.message.text
        self.logger.info(
            "Got message from user %s: %s" % (update.message.from_user.username, query)
        )

        if len(query) < 3:
            response = _("Too short for search, please try again.")
        else:
            response = _("I'm searching for the book: %s") % (query)

        await context.bot.send_message(chat_id=update.message.chat_id, text=response)
        self.logger.info(
            "Send message to user %s: %s"
            % (update.message.from_user.username, response)
        )

        if len(query) < 3:
            return

        books = self.BookFilter(query)
        books_count = books.count()

        if books_count == 0:
            response = _("No results were found for your query, please try again.")
            await context.bot.send_message(
                chat_id=update.message.chat_id, text=response
            )
            self.logger.info(
                "Send message to user %s: %s"
                % (update.message.from_user.username, response)
            )
            return

        response = (
            _(
                "Found %s books.\nI create list, after a few seconds, "
                "select the file to download:"
            )
            % books_count
        )
        await context.bot.send_message(chat_id=update.message.chat_id, text=response)
        self.logger.info(
            "Send message to user %s: %s"
            % (update.message.from_user.username, response)
        )

        pager = self.BookPager(books, 1, query)
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=pager["message"],
            parse_mode="HTML",
            reply_markup=pager["buttons"],
        )

    @cmdtrans
    @CheckAuthDecorator
    async def getBooksPage(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        callback_query = update.callback_query
        query, page_num = callback_query.data.split(query_delimiter, maxsplit=1)
        if page_num == "current":
            return
        try:
            page_num = int(page_num)
        except ValueError:
            page_num = 1

        books = self.BookFilter(query)
        response = self.BookPager(books, page_num, query)
        await context.bot.edit_message_text(
            chat_id=callback_query.message.chat_id,
            message_id=callback_query.message.message_id,
            text=response["message"],
            parse_mode="HTML",
            reply_markup=response["buttons"],
        )
        return

    @cmdtrans
    @CheckAuthDecorator
    async def downloadBooks(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        book_id_set = re.findall(r"\d+$", update.message.text)
        if len(book_id_set) == 1:
            try:
                book_id = int(book_id_set[0])
                book = Book.objects.get(id=book_id)
            except (ValueError, Book.DoesNotExist):
                book_id = None
                book = None
        else:
            book_id = None
            book = None

        if book is None:
            response = _(
                "The book on the link you specified is not found, "
                "try to repeat the book search first."
            )
            await context.bot.send_message(
                chat_id=update.message.chat_id, text=response, parse_mode="HTML"
            )
            self.logger.info("Not find download links: %s" % response)
            return

        authors = ", ".join([a["full_name"] for a in book.authors.values()])
        response = (
            "<b>%(title)s</b>\n%(author)s\n<b>"
            + _("Annotation:")
            + "</b>%(annotation)s\n"
        ) % {
            "title": book.title,
            "author": authors,
            "annotation": book.annotation,
        }

        buttons = [
            InlineKeyboardButton(
                book.format.upper(), callback_data="/getfileorig%s" % book_id
            )
        ]
        if book.format not in settings.NOZIP_FORMATS:
            buttons += [
                InlineKeyboardButton(
                    book.format.upper() + ".ZIP",
                    callback_data="/getfilezip%s" % book_id,
                )
            ]
        if (config.SOPDS_FB2TOEPUB != "") and (book.format == "fb2"):
            buttons += [
                InlineKeyboardButton("EPUB", callback_data="/getfileepub%s" % book_id)
            ]
        if (config.SOPDS_FB2TOMOBI != "") and (book.format == "fb2"):
            buttons += [
                InlineKeyboardButton("MOBI", callback_data="/getfilemobi%s" % book_id)
            ]

        markup = InlineKeyboardMarkup([buttons])
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=response,
            parse_mode="HTML",
            reply_markup=markup,
        )
        self.logger.info("Send download buttons.")
        return

    @cmdtrans
    @CheckAuthDecorator
    async def getBookFile(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        callback_query = update.callback_query
        query = callback_query.data
        book_id_set = re.findall(r"\d+$", query)
        if len(book_id_set) == 1:
            try:
                book_id = int(book_id_set[0])
                book = Book.objects.get(id=book_id)
            except (ValueError, Book.DoesNotExist):
                book = None
        else:
            book = None

        if book is None:
            response = _(
                "The book on the link you specified is not found, "
                "try to repeat the book search first."
            )
            await context.bot.send_message(
                chat_id=callback_query.message.chat_id, text=response, parse_mode="HTML"
            )
            self.logger.info("Not find download links: %s" % response)
            return

        filename = dl.getFileName(book)
        document: Any = None

        if re.match(r"/getfileorig", query):
            document = dl.getFileData(book)
        elif re.match(r"/getfilezip", query):
            document = dl.getFileDataZip(book)
            filename = filename + ".zip"
        elif re.match(r"/getfileepub", query):
            document = dl.getFileDataEpub(book)
            filename = filename + ".epub"
        elif re.match(r"/getfilemobi", query):
            document = dl.getFileDataMobi(book)
            filename = filename + ".mobi"

        if document:
            await context.bot.send_document(
                chat_id=callback_query.message.chat_id,
                document=document,
                filename=filename,
            )
            document.close()
            self.logger.info("Send file: %s" % filename)
        else:
            response = _(
                "There was a technical error, please contact the Bot administrator."
            )
            await context.bot.send_message(
                chat_id=callback_query.message.chat_id, text=response, parse_mode="HTML"
            )
            self.logger.info("Book get error: %s" % response)
            return

        return

    @cmdtrans
    @CheckAuthDecorator
    async def botCallback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query

        if re.match(r"/getfile", query.data):
            return await self.getBookFile(update, context)
        else:
            return await self.getBooksPage(update, context)

    def start(self) -> None:
        quit_command = "CTRL-BREAK" if sys.platform == "win32" else "CONTROL-C"
        self.stdout.write("Quit the sopds_telebot with %s.\n" % quit_command)
        try:
            application = (
                ApplicationBuilder().token(config.SOPDS_TELEBOT_API_TOKEN).build()
            )

            # telegram's typed handler callbacks don't compose cleanly with our
            # decorated, bound async methods, so cast them to Any at registration.
            start_handler = CommandHandler("start", self.startCommand)  # type: ignore
            books_handler = MessageHandler(
                filters.TEXT & ~filters.COMMAND, self.getBooks  # type: ignore
            )
            download_handler = MessageHandler(
                filters.Regex(r"^/download\d+$"), self.downloadBooks  # type: ignore
            )
            callback_handler = CallbackQueryHandler(self.botCallback)  # type: ignore
            application.add_handler(start_handler)
            application.add_handler(books_handler)
            application.add_handler(download_handler)
            application.add_handler(callback_handler)

            application.run_polling()
        except InvalidToken:
            self.stdout.write(
                "Invalid telegram token.\n"
                "Set correct token for telegram API by command:\n"
                " python3 manage.py sopds_util setconf"
                ' SOPDS_TELEBOT_API_TOKEN "<token>"'
            )
            self.logger.error("Invalid telegram token.")
        except (KeyboardInterrupt, SystemExit):
            pass
