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
        else if (element.matches("[data-opds-book-detail]")) renderBookDetail(element, detail);
        renderPagination(element, detail);
    }

    document.querySelectorAll(
        "[data-opds-selector], [data-opds-books], [data-opds-catalogs], [data-opds-book-detail]",
    ).forEach((element) => {
        element.addEventListener("sopds:feed", handleFeed);
        loadOPDS(element).catch(() => {
            if (element.matches("[data-opds-book-detail]")) {
                const loading = element.querySelector("[data-opds-loading]");
                if (loading) loading.hidden = true;
                const errorBox = element.querySelector("[data-opds-error]");
                if (errorBox) {
                    errorBox.textContent = element.dataset.errorLabel || errorBox.textContent;
                    errorBox.hidden = false;
                }
                return;
            }
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

    const catalogIcons = {
        "0": "folder",
        "1": "zip",
        "2": "inpx",
        "3": "inp",
    };

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
            const icon = catalog ? (catalogIcons[entry.catType] || "folder") : "text";
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
        return id ? `/web/details/${id}/` : searchUrl("m", entry.title || "");
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

    function formatLabel(link) {
        const labels = {
            "application/fb2": "fb2",
            "application/fb2+xml": "fb2",
            "application/fb2+zip": "fb2+zip",
            "application/epub+zip": "epub",
            "application/x-mobipocket-ebook": "mobi",
        };
        return labels[link.type] || "download";
    }

    function renderBookDetail(element, detail) {
        const entry = detail.entries[0];
        if (!entry) return;
        element.replaceChildren();

        const article = document.createElement("article");
        article.className = "callout book-detail";
        const row = document.createElement("div");
        row.className = "row book-detail-row";

        const coverCol = document.createElement("div");
        coverCol.className = "small-12 medium-4 large-3 columns book-detail-cover";

        const coverLink = document.createElement("a");
        const bookId = (entry.id || "").split(":").pop();
        const coverUrl = `${element.dataset.coverUrl || "/opds/thumb/"}${bookId}/`;
        coverLink.href = `/opds/cover/${bookId}/`;
        coverLink.setAttribute("aria-label", element.dataset.coverLabel || "Book cover");

        const coverImg = document.createElement("img");
        const imageLink = (entry.links || []).find((link) => link.rel === "http://opds-spec.org/image");
        coverImg.src = imageLink?.href || coverUrl;
        coverImg.alt = entry.title || "";
        coverImg.className = "book-detail-cover__image";
        coverImg.onerror = () => {
            const noCover = element.dataset.noCover || "";
            if (noCover && coverImg.src !== new URL(noCover, window.location).href) {
                coverImg.onerror = null;
                coverImg.src = noCover;
            } else {
                coverImg.onerror = null;
            }
        };
        coverLink.append(coverImg);
        coverCol.append(coverLink);
        row.append(coverCol);

        const metaCol = document.createElement("div");
        metaCol.className = "small-12 medium-8 large-9 columns book-detail-summary";

        const title = document.createElement("h1");
        title.textContent = entry.title || "";
        metaCol.append(title);

        const downloads = (entry.links || []).filter((link) => link.rel === "http://opds-spec.org/acquisition/open-access");
        if (downloads.length) {
            const downloadsDiv = document.createElement("div");
            downloadsDiv.className = "book-detail-downloads";
            downloadsDiv.setAttribute("role", "group");
            downloadsDiv.setAttribute("aria-label", element.dataset.downloadLabel || "Download");
            downloads.forEach((link) => {
                const anchor = document.createElement("a");
                anchor.href = link.href;
                anchor.className = "button small book-download-link";
                anchor.textContent = formatLabel(link);
                downloadsDiv.append(anchor);
            });
            metaCol.append(downloadsDiv);
        }

        function appendLine(labelText, items) {
            if (!items.length) return;
            const term = document.createElement("dt");
            term.textContent = labelText;
            const description = document.createElement("dd");
            items.forEach((item, i) => {
                if (i > 0) description.append(", ");
                if (item.href) {
                    const a = document.createElement("a");
                    a.href = item.href;
                    a.textContent = item.text;
                    description.append(a);
                } else {
                    description.append(item.text);
                }
            });
            metadata.append(term, description);
        }

        const metadata = document.createElement("dl");
        metadata.className = "book-detail-metadata";
        appendLine(
            element.dataset.authorsLabel || "Authors",
            (entry.authors || []).map((author) => ({text: author.name, href: searchUrl("a", author.id)})),
        );
        appendLine(
            element.dataset.seriesLabel || "Series",
            (entry.series || []).map((series) => ({text: series.name, href: searchUrl("s", series.id)})),
        );
        appendLine(
            element.dataset.genresLabel || "Genres",
            (entry.genres || []).map((genre) => ({text: genre.name, href: searchUrl("g", genre.id)})),
        );
        if (entry.filesize) {
            appendLine(element.dataset.fileSizeLabel || "File size", [
                {text: `${entry.filesize} ${element.dataset.fileSizeUnit || "Kb"}`},
            ]);
        }
        if (entry.issued?.trim()) {
            appendLine(element.dataset.publicationDateLabel || "Date", [{text: entry.issued}]);
        }
        metaCol.append(metadata);
        row.append(metaCol);
        article.append(row);

        const parseAnnotation = (html) => {
            if (typeof html !== "string") return null;
            const content = document.createElement("div");
            content.innerHTML = html;
            const text = content.textContent.replace(/\u00a0/gu, " ").trim();
            const media = content.querySelector("img, audio, video, iframe, embed, object");
            return text || media ? content : null;
        };
        const annotation = [entry.annotation, entry.content?.value]
            .map(parseAnnotation)
            .find(Boolean);
        const addAnnotation = (content) => {
            const section = document.createElement("section");
            section.className = "book-detail-annotation";
            const heading = document.createElement("h3");
            heading.textContent = element.dataset.annotationLabel || "Annotation";
            section.append(heading);
            section.append(content);
            article.append(section);
        };
        if (annotation) {
            addAnnotation(annotation);
        } else if (entry.content?.src) {
            const section = document.createElement("section");
            section.className = "book-detail-annotation";
            const heading = document.createElement("h3");
            heading.textContent = element.dataset.annotationLabel || "Annotation";
            section.append(heading);
            const placeholder = document.createElement("p");
            placeholder.className = "book-detail-annotation-loading";
            placeholder.textContent = element.dataset.loadingLabel || "Loading…";
            section.append(placeholder);
            article.append(section);
            fetch(entry.content.src, {credentials: "same-origin"})
                .then((response) => response.ok ? response.text() : "")
                .then((annotation) => {
                    const content = parseAnnotation(annotation);
                    if (content) {
                        placeholder.replaceWith(content);
                    } else section.remove();
                })
                .catch(() => section.remove());
        }

        element.append(article);
    }

    function renderBooks(element, detail, showAnnotation = element.dataset.searchtype === "i") {
        element.replaceChildren();
        detail.entries.forEach((entry) => {
            const heading = document.createElement("div");
            heading.className = "large-12 column book-heading";
            const title = document.createElement("b");
            const titleLink = document.createElement("a");
            titleLink.href = bookUrl(entry);
            titleLink.textContent = entry.title || "";
            title.append(titleLink);
            heading.append(title, " ");
            const downloads = document.createElement("span");
            downloads.className = "book-downloads";
            const downloadsLabel = document.createElement("span");
            downloadsLabel.className = "book-downloads__label";
            downloadsLabel.textContent = `${element.dataset.downloadLabel || "Download"}:`;
            downloads.append(downloadsLabel);
            (entry.links || []).filter((link) => link.rel === "http://opds-spec.org/acquisition/open-access").forEach((link) => {
                const anchor = document.createElement("a");
                anchor.href = link.href;
                anchor.className = "label small book-download-link";
                anchor.textContent = formatLabel(link);
                downloads.append(" ", anchor);
            });
            heading.append(downloads);
            if (element.dataset.isbookshelf === "1") {
                const deleteButton = document.createElement("button");
                deleteButton.type = "button";
                deleteButton.className = "alert label small bookshelf-delete-trigger";
                deleteButton.dataset.bookId = String(entry.id || "").split(":").pop();
                deleteButton.dataset.bookTitle = entry.title || "";
                deleteButton.textContent = element.dataset.deleteLabel || "Delete";
                heading.append(" ", deleteButton);
            }
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
                annotationCell.innerHTML = entry.annotation;
            }
            if (showAnnotation && entry.content?.src) {
                fetch(entry.content.src, {credentials: "same-origin"})
                    .then((response) => response.ok ? response.text() : "")
                    .then((annotation) => {
                        if (!annotation) return;
                        const annotationRow = card.insertRow();
                        const annotationCell = annotationRow.insertCell();
                        annotationCell.colSpan = 2;
                        annotationCell.className = "book-annotation";
                        annotationCell.innerHTML = annotation;
                    })
                    .catch(() => {});
            }
            content.append(card);
            element.append(heading, content);
        });
        renderPagination(element, detail);
    }

    $(document).foundation();
    setSearch();
})(jQuery);
