import {createOpdsClient} from "./opds.js";

(function($) {
    "use strict";

    const opds = createOpdsClient({
        fetch: (...args) => window.fetch(...args),
    });

    async function fetchAnnotation(url) {
        const response = await window.fetch(url, {
            cache: "no-store",
            credentials: "same-origin",
            headers: {Accept: "text/html"},
        });
        if (!response.ok) throw new Error(`Annotation request failed: ${response.status}`);
        return response.text();
    }

    function pageNumber(href) {
        if (!href) return 0;
        const url = new URL(href, window.location);
        const queryPage = Number(url.searchParams.get("page"));
        if (queryPage > 0) return queryPage;
        const finalSegment = url.pathname.split("/").filter(Boolean).at(-1);
        return /^\d+$/u.test(finalSegment || "") ? Number(finalSegment) : 1;
    }

    function withPagination(detail) {
        const linkByRel = (...relations) => detail.links.find(
            (link) => relations.includes(link.rel),
        );
        const previousPage = pageNumber(linkByRel("previous", "prev")?.href);
        const nextPage = pageNumber(linkByRel("next")?.href);
        const page = previousPage
            ? previousPage + 1
            : nextPage
                ? Math.max(1, nextPage - 1)
                : pageNumber(linkByRel("self")?.href) || 1;
        return {
            ...detail,
            page,
            pages: pageNumber(linkByRel("last")?.href) || page,
        };
    }

    const annotationTags = new Set([
        "a", "b", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3",
        "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre", "span",
        "strong", "sub", "sup", "table", "tbody", "td", "th", "thead", "tr", "ul",
    ]);

    function safeAnnotationUrl(value) {
        return /^\s*(?:javascript|vbscript):/iu.test(value) ? null : value;
    }

    function annotationContent(value, type = "text/plain") {
        if (typeof value !== "string") return null;
        const content = document.createElement("div");
        if (type === "text/html" || type === "application/xhtml+xml") {
            content.innerHTML = value;
            content.querySelectorAll("script, style, iframe, object, embed, link, meta, base").forEach((node) => node.remove());
            content.querySelectorAll("*").forEach((node) => {
                if (!annotationTags.has(node.localName)) {
                    node.replaceWith(...node.childNodes);
                    return;
                }
                [...node.attributes].forEach((attribute) => {
                    const {name, value: attributeValue} = attribute;
                    if (["class", "dir", "lang", "title"].includes(name)) return;
                    if (name === "href" && node.localName === "a") {
                        if (safeAnnotationUrl(attributeValue)) return;
                    }
                    if (name === "src" && node.localName === "img") {
                        if (safeAnnotationUrl(attributeValue)) return;
                    }
                    if (name === "alt" && node.localName === "img") return;
                    node.removeAttribute(name);
                });
            });
        } else {
            content.textContent = value;
        }
        const text = content.textContent.replace(/\u00a0/gu, " ").trim();
        return text || content.querySelector("img") ? content : null;
    }

    async function loadOPDS(element) {
        const detail = withPagination(await opds.fetchFeed(element.dataset.feedUrl));
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
        const detail = await opds.fetchFeed(`/opds/search/books/i/${bookId}/`);
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

    function pathParts(href) {
        return new URL(href, window.location).pathname
            .split("/")
            .filter(Boolean)
            .map((part) => decodeURIComponent(part));
    }

    function webSearchUrl(searchtype, searchterms, searchterms0) {
        const url = new URL("/web/search/books/", window.location);
        url.searchParams.set("searchtype", searchtype);
        url.searchParams.set("searchterms", searchterms);
        if (searchterms0 !== undefined) url.searchParams.set("searchterms0", searchterms0);
        return `${url.pathname}${url.search}`;
    }

    function webHref(link, element) {
        if (!link?.href) return "";
        const parts = pathParts(link.href);
        if (parts[0] !== "opds") return link.href;
        const [, resource, ...rest] = parts;
        if (["books", "authors", "series"].includes(resource)) {
            const selectorUrl = element?.dataset.selectorUrl || `/web/${resource.slice(0, -1)}/`;
            const url = new URL(selectorUrl, window.location);
            if (rest[0] !== undefined) url.searchParams.set("lang", rest[0]);
            if (rest.length > 1) url.searchParams.set("chars", rest.slice(1).join("/"));
            return `${url.pathname}${url.search}`;
        }
        if (resource === "genres") {
            const url = new URL(element?.dataset.selectorUrl || "/web/genre/", window.location);
            if (rest[0] !== undefined) url.searchParams.set("section", rest[0]);
            return `${url.pathname}${url.search}`;
        }
        if (resource === "catalogs") {
            const url = new URL(element?.dataset.pageUrl || "/web/catalogs/", window.location);
            if (rest[0] !== undefined) url.searchParams.set("cat", rest[0]);
            return `${url.pathname}${url.search}`;
        }
        if (resource !== "search") return link.href;
        const [entity, searchtype, ...terms] = rest;
        if (entity === "books") {
            if (searchtype === "as" && terms.length === 1) return webSearchUrl("a", terms[0]);
            return webSearchUrl(searchtype, terms[0] || "", terms[1]);
        }
        const searchUrl = entity === "authors"
            ? "/web/search/authors/"
            : entity === "series"
                ? "/web/search/series/"
                : element?.dataset.searchUrl || "/web/search/books/";
        const url = new URL(searchUrl, window.location);
        url.searchParams.set("searchtype", searchtype || "m");
        url.searchParams.set("searchterms", terms[0] || "");
        return `${url.pathname}${url.search}`;
    }

    function relatedEntities(entry, kind) {
        return (entry.links || [])
            .filter((link) => link.rel === "related" && pathParts(link.href).at(-2) === kind)
            .map((link) => ({
                name: (link.title || "").replace(/^[^:]+:\s*/u, ""),
                href: webHref(link),
            }));
    }

    function fileSize(entry) {
        const acquisition = (entry.links || []).find(
            (link) => link.rel.startsWith("http://opds-spec.org/acquisition"),
        );
        return acquisition?.length ? String(Math.floor(acquisition.length / 1000)) : "";
    }

    function catalogType(entry) {
        return (entry.categories || []).find(
            (category) => category.scheme === "urn:sopds:catalog-type",
        )?.term || "";
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
            const title = entry.title || "";
            const opdsNavigation = (entry.links || []).find((item) => ["subsection", "alternate"].includes(item.rel));
            const targetUrl = webHref(opdsNavigation, element);
            const current = targetUrl && new URL(targetUrl, window.location).href === window.location.href;
            const link = document.createElement(current ? "span" : "a");
            link.className = "selector-link";
            if (current) {
                link.classList.add("selector-link--current");
                link.setAttribute("aria-current", "page");
            }
            else if (targetUrl) link.href = targetUrl;
            const titleNode = document.createElement("span");
            titleNode.className = "selector-link__title";
            titleNode.textContent = title;
            link.append(titleNode, " ");
            const count = document.createElement("span");
            count.className = "selector-link__count";
            count.textContent = entry.content?.value || "";
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
            const icon = catalog ? (catalogIcons[catalogType(entry)] || "folder") : "text";
            image.src = `/static/images/${icon}.png`;
            image.alt = "";
            link.append(image);
            link.href = webHref(catalog, element);
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

    function bookUrl(entry) {
        const id = String(entry.id || "").split(":").pop();
        return id ? `/web/details/${id}/` : "";
    }

    function appendBookMetadata(container, className, label, values) {
        const text = values.filter(Boolean).join(", ");
        if (!text) return;
        const line = document.createElement("div");
        line.className = `book-card__metadata ${className}`;
        line.setAttribute("aria-label", `${label}: ${text}`);
        line.textContent = text;
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
            (entry.authors || []).map((author) => ({text: author.name, href: webHref({href: author.uri})})),
        );
        appendLine(
            element.dataset.seriesLabel || "Series",
            relatedEntities(entry, "s").map((series) => ({text: series.name, href: series.href})),
        );
        appendLine(
            element.dataset.genresLabel || "Genres",
            relatedEntities(entry, "g").map((genre) => ({text: genre.name, href: genre.href})),
        );
        if (fileSize(entry)) {
            appendLine(element.dataset.fileSizeLabel || "File size", [
                {text: `${fileSize(entry)} ${element.dataset.fileSizeUnit || "Kb"}`},
            ]);
        }
        if (entry.issued?.trim()) {
            appendLine(element.dataset.publicationDateLabel || "Date", [{text: entry.issued}]);
        }
        metaCol.append(metadata);
        row.append(metaCol);
        article.append(row);

        const annotation = [
            {value: entry.summary, type: "text/html"},
            entry.content,
        ]
            .map((content) => annotationContent(content?.value, content?.type))
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
            fetchAnnotation(entry.content.src)
                .then((annotation) => {
                    const content = annotationContent(annotation, entry.content.type);
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
            const content = document.createElement("div");
            content.className = "book-result";
            const card = document.createElement("a");
            card.className = "book-card book-list-card";
            card.href = bookUrl(entry);
            const cover = document.createElement("div");
            cover.className = "book-card__cover";
            const image = opdsLink(entry, "http://opds-spec.org/image/thumbnail")
                || opdsLink(entry, "http://opds-spec.org/thumbnail");
            if (image) {
                const img = document.createElement("img");
                img.className = "book-card__image";
                img.src = image.href;
                img.alt = entry.title || "";
                img.onerror = () => {
                    const noCover = element.dataset.noCover || "";
                    if (noCover && img.src !== new URL(noCover, window.location).href) {
                        img.onerror = null;
                        img.src = noCover;
                        return;
                    }
                    img.onerror = null;
                    img.classList.add("book-card__image--fallback");
                };
                cover.append(img);
            } else {
                cover.classList.add("book-card__cover--empty");
            }
            const metadata = document.createElement("div");
            metadata.className = "book-card__body";
            const title = document.createElement("h2");
            title.className = "book-card__title";
            title.textContent = entry.title || "";
            metadata.append(title);
            appendBookMetadata(metadata, "book-card__authors", element.dataset.authorsLabel, (entry.authors || []).map((author) => author.name));
            appendBookMetadata(metadata, "book-card__genres", element.dataset.genresLabel, relatedEntities(entry, "g").map((genre) => genre.name));
            appendBookMetadata(metadata, "book-card__date", element.dataset.publicationDateLabel, [entry.issued?.trim()]);
            card.append(cover, metadata);

            const actions = document.createElement("div");
            actions.className = "book-card__actions";
            if (element.dataset.isbookshelf === "1") {
                const downloads = (entry.links || []).filter((link) => link.rel === "http://opds-spec.org/acquisition/open-access");
                downloads.forEach((link) => {
                    const anchor = document.createElement("a");
                    anchor.href = link.href;
                    anchor.className = "label small book-download-link";
                    anchor.textContent = formatLabel(link);
                    actions.append(anchor);
                });
                const deleteButton = document.createElement("button");
                deleteButton.type = "button";
                deleteButton.className = "alert label small bookshelf-delete-trigger";
                deleteButton.dataset.bookId = String(entry.id || "").split(":").pop();
                deleteButton.dataset.bookTitle = entry.title || "";
                deleteButton.textContent = element.dataset.deleteLabel || "Delete";
                actions.append(deleteButton);
            }
            content.append(card);
            if (actions.childElementCount) content.append(actions);

            const appendAnnotation = (value, type) => {
                const annotation = annotationContent(value, type);
                if (!annotation) return;
                const annotationCell = document.createElement("div");
                annotationCell.className = "book-annotation";
                annotationCell.append(annotation);
                content.append(annotationCell);
            };
            if (showAnnotation) {
                const annotation = [
                    {value: entry.summary, type: "text/html"},
                    entry.content,
                ].find((item) => annotationContent(item?.value, item?.type));
                if (annotation) appendAnnotation(annotation.value, annotation.type);
            }
            if (showAnnotation && !entry.summary && !entry.content?.value && entry.content?.src) {
                fetchAnnotation(entry.content.src)
                    .then((annotation) => {
                        appendAnnotation(annotation, entry.content.type);
                    })
                    .catch(() => {});
            }
            element.append(content);
        });
        renderPagination(element, detail);
    }

    $(document).foundation();
    setSearch();
})(jQuery);
