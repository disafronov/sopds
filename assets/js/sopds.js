import {createOpdsClient} from "./opds.js";

(function() {
    "use strict";

    const opds = createOpdsClient({
        fetch: (...args) => window.fetch(...args),
    });

    function matchDesktopLayoutToMenu() {
        const menu = document.getElementById("main_menu");
        const isDesktop = window.matchMedia?.("(min-width: 64em)")?.matches;
        if (!menu || !isDesktop) {
            document.documentElement.style.removeProperty("--sopds-menu-width");
            return;
        }

        const width = menu.scrollWidth;
        if (width) {
            document.documentElement.style.setProperty(
                "--sopds-menu-width",
                `${width}px`,
            );
        }
    }

    matchDesktopLayoutToMenu();
    window.addEventListener("resize", matchDesktopLayoutToMenu);

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
            const lastChild = content.lastElementChild;
            if (
                lastChild?.localName === "p"
                && !lastChild.textContent.replace(/\u00a0/gu, " ").trim()
                && !lastChild.querySelector("img")
            ) {
                lastChild.remove();
            }
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
        closeSearchDropdown();
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

    document.addEventListener("click", function(event) {
        const searchToggle = event.target.closest(".search-dropdown-toggle");
        if (searchToggle) {
            toggleSearchDropdown(searchToggle);
            return;
        }

        if (!event.target.closest(".top-bar-search")) closeSearchDropdown();

        if (!event.target.closest('#main_menu, .menu-icon[aria-controls="main_menu"]')) {
            closeMainMenu();
        }

        const menuToggle = event.target.closest('.menu-icon[aria-controls="main_menu"]');
        if (menuToggle) {
            closeSearchDropdown();
            const menu = document.getElementById("main_menu");
            const isOpen = menu.classList.toggle("is-open");
            menuToggle.setAttribute("aria-expanded", String(isOpen));
            return;
        }

        const submenuToggle = event.target.closest(".sopdsmenu__submenu-toggle");
        if (submenuToggle) {
            const item = submenuToggle.closest("li");
            const isOpen = item.classList.toggle("is-open");
            if (isOpen) {
                item.parentElement?.querySelectorAll(":scope > li.is-open").forEach((sibling) => {
                    if (sibling === item) return;
                    sibling.classList.remove("is-open");
                    sibling.querySelector(".sopdsmenu__submenu-toggle")?.setAttribute("aria-expanded", "false");
                });
            }
            submenuToggle.setAttribute("aria-expanded", String(isOpen));
            return;
        }

        const dialogTrigger = event.target.closest("[data-dialog-open]");
        if (dialogTrigger) {
            document.getElementById(dialogTrigger.dataset.dialogOpen)?.showModal();
            return;
        }

        const dialogClose = event.target.closest("[data-dialog-close]");
        if (dialogClose) {
            dialogClose.closest("dialog")?.close();
            return;
        }

        const trigger = event.target.closest(".bookshelf-delete-trigger");
        if (!trigger) {
            return;
        }
        const modal = document.getElementById("DeleteBookModal");
        const bookId = trigger.dataset.bookId;
        document.getElementById("DeleteBook_book").value = bookId;
        document.getElementById("DeleteBook_image").src = `${modal.dataset.coverUrl}${bookId}/`;
        document.getElementById("DeleteBook_title").textContent = trigger.dataset.bookTitle || "";
        modal.showModal();
    });

    function closeSearchDropdown() {
        const dropdown = document.getElementById("search-dropdown");
        const toggle = document.querySelector(".search-dropdown-toggle");
        if (!dropdown || !toggle) return;
        dropdown.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
    }

    function closeMainMenu() {
        const menu = document.getElementById("main_menu");
        const toggle = document.querySelector('.menu-icon[aria-controls="main_menu"]');
        if (!menu || !toggle) return;
        menu.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
    }

    function toggleSearchDropdown(toggle) {
        const dropdown = document.getElementById(toggle.getAttribute("aria-controls"));
        if (!dropdown) return;
        if (dropdown.hidden) closeMainMenu();
        dropdown.hidden = !dropdown.hidden;
        toggle.setAttribute("aria-expanded", String(!dropdown.hidden));
    }

    document.addEventListener("keydown", function(event) {
        if (event.key !== "Escape") return;
        closeSearchDropdown();
        closeMainMenu();
    });

    document.querySelectorAll("dialog").forEach((dialog) => {
        dialog.addEventListener("click", (event) => {
            if (event.target === dialog) dialog.close();
        });
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

    function webPageHref(link, element) {
        const page = pageNumber(link?.href);
        if (!page) return "";
        const url = new URL(element.dataset.pageUrl, window.location);
        if (element.dataset.mode === "catalogs" && element.dataset.catId) {
            url.searchParams.set("cat", element.dataset.catId);
        } else {
            url.searchParams.set("searchtype", element.dataset.searchtype);
            url.searchParams.set("searchterms", element.dataset.searchterms);
            if (element.dataset.searchterms0) {
                url.searchParams.set("searchterms0", element.dataset.searchterms0);
            }
        }
        url.searchParams.set("page", page);
        return `${url.pathname}${url.search}`;
    }

    function renderPagination(element, detail) {
        const targets = document.querySelectorAll("[data-opds-pagination]");
        if (!targets.length) return;
        const first = opdsLink(detail, "first");
        const previous = opdsLink(detail, "previous") || opdsLink(detail, "prev");
        const next = opdsLink(detail, "next");
        const last = opdsLink(detail, "last");
        const hasMultiplePages = previous
            || next
            || (first && last && pageNumber(first.href) !== pageNumber(last.href));
        if (!hasMultiplePages) {
            targets.forEach((target) => {
                target.hidden = true;
                target.replaceChildren();
            });
            return;
        }
        targets.forEach((target) => {
            target.hidden = false;
            const list = document.createElement("div");
            list.className = "opds-pagination";
            const before = document.createElement("div");
            before.className = "opds-pagination__before";
            const after = document.createElement("div");
            after.className = "opds-pagination__after";
            const shownPages = new Set([detail.page]);
            const addPageLink = (group, link, className, label) => {
                const page = pageNumber(link?.href);
                if (!link || shownPages.has(page)) return;
                shownPages.add(page);
                const item = document.createElement("span");
                item.className = className;
                const anchor = document.createElement("a");
                anchor.href = webPageHref(link, element);
                anchor.dataset.page = String(page);
                anchor.setAttribute("aria-label", label);
                anchor.textContent = anchor.dataset.page;
                item.append(anchor);
                group.append(item);
            };
            addPageLink(before, first, "pagination-first", target.dataset.firstLabel);
            addPageLink(before, previous, "pagination-previous", target.dataset.previousLabel);
            const current = document.createElement("span");
            current.className = "current";
            current.textContent = String(detail.page);
            addPageLink(after, next, "pagination-next", target.dataset.nextLabel);
            addPageLink(after, last, "pagination-last", target.dataset.lastLabel);
            list.append(before, current, after);
            target.replaceChildren(list);
        });
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

    function renderCatalogBreadcrumb(element, detail) {
        if (!element.dataset.catId) return;
        const breadcrumbs = document.querySelector(".breadcrumbs");
        const path = String(detail.title || "").split("|").at(-1)?.trim();
        if (!breadcrumbs || !path) return;
        breadcrumbs.querySelector("[data-opds-catalog-path]")?.remove();
        const item = document.createElement("li");
        item.dataset.opdsCatalogPath = "";
        item.textContent = path;
        breadcrumbs.append(item);
    }

    function renderCatalogs(element, detail) {
        const body = element.tBodies[0];
        body.replaceChildren();
        renderCatalogBreadcrumb(element, detail);
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
            link.href = catalog ? webHref(catalog, element) : bookUrl(entry);
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

        function appendLine(metadata, labelText, items) {
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
            metadata,
            element.dataset.authorsLabel || "Authors",
            (entry.authors || []).map((author) => ({text: author.name, href: webHref({href: author.uri})})),
        );
        appendLine(
            metadata,
            element.dataset.seriesLabel || "Series",
            relatedEntities(entry, "s").map((series) => ({text: series.name, href: series.href})),
        );
        appendLine(
            metadata,
            element.dataset.genresLabel || "Genres",
            relatedEntities(entry, "g").map((genre) => ({text: genre.name, href: genre.href})),
        );
        if (entry.issued?.trim()) {
            appendLine(metadata, element.dataset.publicationDateLabel || "Date", [{text: entry.issued}]);
        }
        if (fileSize(entry)) {
            appendLine(metadata, element.dataset.fileSizeLabel || "File size", [
                {text: `${fileSize(entry)} ${element.dataset.fileSizeUnit || "Kb"}`},
            ]);
        }
        metaCol.append(metadata);

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

            if (element.dataset.isbookshelf === "1") {
                content.classList.add("book-result--bookshelf");
                const deleteButton = document.createElement("button");
                deleteButton.type = "button";
                deleteButton.className = "bookshelf-delete-trigger";
                deleteButton.dataset.bookId = String(entry.id || "").split(":").pop();
                deleteButton.dataset.bookTitle = entry.title || "";
                deleteButton.textContent = element.dataset.deleteLabel || "Delete";
                content.append(card, deleteButton);
            } else {
                content.append(card);
            }

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

    setSearch();
})();
