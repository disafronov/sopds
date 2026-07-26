import {fetchFeed} from "./opds.js";

(function($) {
    "use strict";

    async function loadOPDS(element) {
        const detail = await fetchFeed(element.dataset.feedUrl);
        const CustomEventClass = element.ownerDocument.defaultView.CustomEvent;
        element.dispatchEvent(new CustomEventClass("sopds:feed", {detail}));
    }

    function handleFeed(event) {
        const element = event.target;
        const detail = event.detail;
        if (element.matches("[data-opds-catalogs]")) renderCatalogs(element, detail);
        else if (element.matches("[data-opds-books]")) renderBooks(element, detail);
        else if (element.matches("[data-opds-selector]")) renderSelector(element, detail);
        renderPagination(element, detail);
    }

    document.querySelectorAll(
        "[data-opds-selector], [data-opds-books], [data-opds-catalogs]",
    ).forEach((element) => {
        element.addEventListener("sopds:feed", handleFeed);
        loadOPDS(element).catch(() => {
        element.hidden = true;
        const errorBox = document.querySelector("[data-opds-error]");
        if (errorBox) errorBox.hidden = false;
        });
    });

    async function loadFooterBook(element) {
        const bookId = element.dataset.bookId;
        const detail = await fetchFeed(`/opds/search/books/i/${bookId}/`);
        const rendered = document.createElement("div");
        for (const [name, value] of Object.entries(element.dataset)) {
            rendered.dataset[name] = value;
        }
        renderBooks(rendered, detail, false);
        const card = rendered.querySelector(".book-card");
        if (card) {
            card.classList.add("footer-book-card");
            element.replaceChildren(card);
        }
    }

    document.querySelectorAll("[data-opds-footer-book]").forEach((element) => {
        loadFooterBook(element).catch(() => {
            element.replaceChildren();
        });
    });

    function setSearch() {
        const selected = document.querySelector(
            'input[name="searchtype"]:checked',
        );
        const form = document.getElementById("searchform");
        const searchBox = document.getElementById("main_searchbox");

        if (!selected || !form || !searchBox) {
            return;
        }

        form.action = selected.dataset.searchUrl;
        searchBox.placeholder = `Search by ${selected.id}`;
        $("#search-dropdown").foundation("close");
    }

    document
        .querySelectorAll('input[name="searchtype"]')
        .forEach(function(input) {
            input.addEventListener("change", setSearch);
        });

    document
        .querySelectorAll(".clickable-rows tbody tr")
        .forEach(function(row) {
            row.addEventListener("click", function(event) {
                if (
                    event.target.closest(
                        "a, button, input, select, textarea",
                    )
                ) {
                    return;
                }

                const link = row.querySelector("a[href]");
                if (link) {
                    window.location.assign(link.href);
                }
            });
        });

    document
        .querySelectorAll(".bookshelf-delete-trigger")
        .forEach(function(trigger) {
            trigger.addEventListener("click", function() {
                const modal = $("#DeleteBookModal");
                const bookId = trigger.dataset.bookId;

                $("#DeleteBook_book").val(bookId);
                $("#DeleteBook_image").attr(
                    "src",
                    `${modal[0].dataset.coverUrl}${bookId}/`,
                );
                $("#DeleteBook_title").text(trigger.dataset.bookTitle);
                modal.foundation("open");
            });
        });

    document.addEventListener("click", function(event) {
        const trigger = event.target.closest(".bookshelf-delete-trigger");
        if (!trigger) {
            return;
        }
        const modal = $("#DeleteBookModal");
        const bookId = trigger.dataset.bookId;
        $("#DeleteBook_book").val(bookId);
        $("#DeleteBook_image").attr(
            "src",
            `${modal[0].dataset.coverUrl}${bookId}/`,
        );
        $("#DeleteBook_title").text(trigger.dataset.bookTitle || "");
        modal.foundation("open");
    });

    function opdsLink(entry, rel) {
        return (entry.links || []).find((link) => link.rel === rel);
    }

    function pageUrl(element, page) {
        const url = new URL(element.dataset.pageUrl, window.location);
        if (element.dataset.mode === "catalogs" && element.dataset.catId) {
            url.searchParams.set("cat", element.dataset.catId);
        } else {
            url.searchParams.set("searchtype", element.dataset.searchtype);
            url.searchParams.set("searchterms", element.dataset.searchterms);
        }
        url.searchParams.set("page", page);
        return `${url.pathname}${url.search}`;
    }

    function renderPagination(element, detail) {
        const target = document.querySelector("[data-opds-pagination]");
        if (!target || detail.pages <= 1) return;
        const list = document.createElement("ul");
        list.className = "pagination";
        const previous = document.createElement("li");
        previous.className = "pagination-previous";
        previous.textContent = target.dataset.previousLabel;
        if (detail.page > 1) {
            const link = document.createElement("a");
            link.href = pageUrl(element, detail.page - 1);
            link.textContent = target.dataset.previousLabel;
            previous.replaceChildren(link);
        } else previous.className = "disabled";
        list.append(previous);
        for (let number = 1; number <= detail.pages; number += 1) {
            const item = document.createElement("li");
            if (number === detail.page) item.className = "current";
            else {
                const link = document.createElement("a");
                link.href = pageUrl(element, number);
                link.textContent = String(number);
                item.append(link);
            }
            if (number === detail.page) item.textContent = String(number);
            list.append(item);
        }
        const next = document.createElement("li");
        next.className = "pagination-next";
        next.textContent = target.dataset.nextLabel;
        if (detail.page < detail.pages) {
            const link = document.createElement("a");
            link.href = pageUrl(element, detail.page + 1);
            link.textContent = target.dataset.nextLabel;
            next.replaceChildren(link);
        } else next.className = "disabled";
        list.append(next);
        target.replaceChildren(list);
    }

    function renderSelector(element, detail) {
        const body = element.tBodies[0];
        body.replaceChildren();
        detail.entries.forEach((entry) => {
            const row = body.insertRow();
            const cell = row.insertCell();
            const link = document.createElement("a");
            link.className = "selector-link";
            const title = entry.title || "";
            const href = (entry.links || []).find((item) => ["subsection", "alternate"].includes(item.rel))?.href || "";
            let url;
            if (element.dataset.mode === "genre") {
                const pathParts = new URL(href, window.location).pathname.split("/").filter(Boolean);
                url = new URL(pathParts[1] === "genres" ? element.dataset.selectorUrl : element.dataset.searchUrl, window.location);
                if (pathParts[1] === "genres") url.searchParams.set("section", pathParts[2]);
                else {
                    url.searchParams.set("searchtype", "g");
                    url.searchParams.set("searchterms", pathParts.at(-1));
                }
            } else if (element.dataset.mode === "entity") {
                url = new URL(element.dataset.searchUrl, window.location);
                url.searchParams.set("searchtype", element.dataset.entity === "author" ? "a" : "s");
                url.searchParams.set("searchterms", (entry.id || "").split(":").pop());
            } else {
                const kindPath = `/opds/${element.dataset.feedKind}/`;
                if (href.startsWith(kindPath)) {
                    url = new URL(element.dataset.selectorUrl, window.location);
                    url.searchParams.set("lang", element.dataset.langCode);
                    url.searchParams.set("chars", title);
                } else {
                    url = new URL(element.dataset.searchUrl, window.location);
                    const emptySearch = href.includes("/e/__sopds_empty__/");
                    url.searchParams.set("searchtype", emptySearch ? "e" : "b");
                    url.searchParams.set(
                        "searchterms",
                        emptySearch ? "__sopds_empty__" : title,
                    );
                }
            }
            link.href = `${url.pathname}${url.search}`;
            link.append(document.createTextNode(title), " ");
            const count = document.createElement("span");
            count.className = "selector-link__count";
            const match = (entry.content?.value || "").match(/\d+/u);
            count.textContent = (element.dataset.countLabel || "").replace("%(count)s", match ? match[0] : "");
            link.append(count);
            cell.append(link);
        });
        if (element.dataset.mode === "genre") {
            const parent = detail.links.find((link) => link.rel === "up");
            const breadcrumbs = document.querySelector(".breadcrumbs");
            if (parent && breadcrumbs) {
                const item = document.createElement("li");
                item.textContent = parent.title || "";
                breadcrumbs.append(item);
            }
        }
        renderPagination(element, detail);
    }

    function renderCatalogs(element, detail) {
        const body = element.tBodies[0];
        body.replaceChildren();
        detail.entries.forEach((entry) => {
            const row = body.insertRow();
            const catalog = opdsLink(entry, "subsection");
            const cell = row.insertCell();
            const link = document.createElement("a");
            link.className = "selector-link";
            const image = document.createElement("img");
            image.className = "selector-link__icon";
            const icon = catalog ? "folder" : "text";
            image.src = `/static/images/${icon}.png`;
            image.alt = "";
            link.append(image);
            const url = new URL(element.dataset.pageUrl, window.location);
            if (catalog) url.searchParams.set("cat", catalog.href.split("/").filter(Boolean).pop());
            else {
                url.pathname = "/web/search/books/";
                url.searchParams.set("searchtype", "i");
                url.searchParams.set("searchterms", (entry.id || "").split(":").pop());
            }
            link.href = `${url.pathname}${url.search}`;
            link.append(document.createTextNode(entry.title || ""));
            cell.append(link);
            row.addEventListener("click", (event) => {
                if (!event.target.closest("a, button, input, select, textarea")) {
                    window.location.assign(link.href);
                }
            });
        });
        renderPagination(element, detail);
    }

    function searchUrl(type, id) {
        const url = new URL("/web/search/books/", window.location);
        url.searchParams.set("searchtype", type);
        url.searchParams.set("searchterms", String(id).trim().replace(/\s+/gu, " "));
        return `${url.pathname}${url.search}`;
    }

    function bookUrl(entry) {
        const id = String(entry.id || "").split(":").pop();
        return id ? searchUrl("i", id) : searchUrl("m", entry.title || "");
    }

    function appendMetadataLine(container, label, values) {
        if (!values.length) return;
        const line = document.createElement("div");
        const heading = document.createElement("b");
        heading.textContent = `${label}: `;
        line.append(heading);
        values.forEach((value, index) => {
            if (index) line.append(document.createTextNode(", "));
            if (value.href) {
                const link = document.createElement("a");
                link.href = value.href;
                link.textContent = value.text;
                line.append(link);
            } else {
                line.append(document.createTextNode(value.text));
            }
        });
        container.append(line);
    }

    function formatLabel(link, index) {
        const type = link.type || "download";
        if (type === "application/fb2+xml") return index === 0 ? "fb2" : "fb2+zip";
        if (type === "application/epub+zip") return index === 0 ? "epub" : "epub+zip";
        return type.split("/").pop();
    }

    function renderBooks(element, detail, showAnnotation = element.dataset.searchtype === "i") {
        element.replaceChildren();
        detail.entries.forEach((entry) => {
            const heading = document.createElement("div");
            heading.className = "large-12 column";
            const title = document.createElement("b");
            const titleLink = document.createElement("a");
            titleLink.href = bookUrl(entry);
            titleLink.textContent = entry.title || "";
            title.append(titleLink);
            heading.append(title, " Download: ");
            (entry.links || []).filter((link) => link.rel === "http://opds-spec.org/acquisition/open-access").forEach((link, index) => {
                const anchor = document.createElement("a");
                anchor.href = link.href;
                anchor.className = "label small";
                anchor.textContent = formatLabel(link, index);
                heading.append(anchor, " ");
            });
            const content = document.createElement("div");
            content.className = "large-12 column";
            const card = document.createElement("table");
            card.className = "book-card book-list-card";
            const row = card.insertRow();
            const imageCell = row.insertCell();
            imageCell.width = "100";
            const image = opdsLink(entry, "http://opds-spec.org/image/thumbnail")
                || opdsLink(entry, "http://opds-spec.org/thumbnail");
            if (image) {
                const img = document.createElement("img");
                img.className = "thumbnail";
                img.src = image.href;
                img.alt = entry.title || "";
                imageCell.append(img);
            }
            const textCell = row.insertCell();
            textCell.style.cssText = "font-size:80%; padding:0rem 1rem;";
            appendMetadataLine(textCell, element.dataset.bookNameLabel, [{
                text: entry.title || "",
                href: bookUrl(entry),
            }]);
            appendMetadataLine(
                textCell,
                element.dataset.authorsLabel,
                (entry.authors || []).map((author) => ({
                    text: author.name,
                    href: searchUrl("a", author.id),
                })),
            );
            appendMetadataLine(
                textCell,
                element.dataset.seriesLabel,
                (entry.series || []).map((series) => ({
                    text: series.name,
                    href: searchUrl("s", series.id),
                })),
            );
            appendMetadataLine(
                textCell,
                element.dataset.genresLabel,
                (entry.genres || []).map((genre) => ({
                    text: genre.name,
                    href: searchUrl("g", genre.id),
                })),
            );
            appendMetadataLine(textCell, element.dataset.fileSizeLabel, [{
                text: `${entry.filesize || "0"} ${element.dataset.fileSizeUnit}`,
            }]);
            appendMetadataLine(textCell, element.dataset.publicationDateLabel, [{
                text: entry.issued || "",
            }]);
            if (showAnnotation && entry.annotation) {
                const annotationRow = card.insertRow();
                const annotationCell = annotationRow.insertCell();
                annotationCell.colSpan = 2;
                annotationCell.className = "book-annotation";
                annotationCell.textContent = entry.annotation;
            }
            content.append(card);
            element.append(heading, content);
        });
        renderPagination(element, detail);
    }

    $(document).foundation();
    setSearch();
})(jQuery);
