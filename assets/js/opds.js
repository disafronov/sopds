import { XMLParser } from "fast-xml-parser";

const parser = new XMLParser({
    ignoreAttributes: false,
    stopNodes: ["feed.entry.content"],
});

function list(value) {
    return value === undefined ? [] : Array.isArray(value) ? value : [value];
}

function text(value) {
    if (typeof value === "object" && value !== null) {
        return text(value["#text"]);
    }
    return value === undefined || value === null ? "" : String(value);
}

function decodeContent(value) {
    const area = document.createElement("textarea");
    area.innerHTML = String(value).replace(/^<!\[CDATA\[|\]\]>$/gu, "");
    return area.value;
}

function pageNumber(href) {
    if (!href) return 0;
    const url = new URL(href, window.location);
    const queryPage = Number(url.searchParams.get("page"));
    if (queryPage > 0) return queryPage;
    const finalSegment = url.pathname.split("/").filter(Boolean).at(-1);
    return /^\d+$/u.test(finalSegment || "") ? Number(finalSegment) : 1;
}

function seriesFromLinks(links) {
    return links
        .filter((link) => {
            if (link.rel !== "related") return false;
            const parts = new URL(link.href, window.location).pathname
                .split("/")
                .filter(Boolean);
            return parts.at(-2) === "s";
        })
        .map((link) => ({
            id: new URL(link.href, window.location).pathname
                .split("/")
                .filter(Boolean)
                .at(-1) || "",
            name: (link.title || "").replace(/^[^:]+:\s*/u, ""),
        }));
}

function genresFromLinks(links) {
    return links
        .filter((link) => {
            if (link.rel !== "related") return false;
            const parts = new URL(link.href, window.location).pathname
                .split("/")
                .filter(Boolean);
            return parts.at(-2) === "g";
        })
        .map((link) => ({
            id: new URL(link.href, window.location).pathname
                .split("/")
                .filter(Boolean)
                .at(-1) || "",
            name: (link.title || "").replace(/^[^:]+:\s*/u, ""),
        }));
}

export function parseFeed(xml) {
    const feed = parser.parse(xml).feed || {};
    const feedLinks = list(feed.link).map((link) => ({
        href: link["@_href"] || "",
        rel: link["@_rel"] || "",
        type: link["@_type"] || undefined,
        title: link["@_title"] || undefined,
    }));
    const linkByRel = (...relations) => feedLinks.find(
        (link) => relations.includes(link.rel),
    );
    const previousPage = pageNumber(linkByRel("previous", "prev")?.href);
    const nextPage = pageNumber(linkByRel("next")?.href);
    const currentPage = previousPage
        ? previousPage + 1
        : nextPage
            ? Math.max(1, nextPage - 1)
            : pageNumber(linkByRel("self")?.href) || 1;
    const lastPage = pageNumber(linkByRel("last")?.href) || currentPage;
    const entries = list(feed.entry).map((entry) => {
        const categories = list(entry.category);
        const links = list(entry.link).map((link) => ({
            href: link["@_href"] || "",
            rel: link["@_rel"] || "",
            type: link["@_type"] || undefined,
            title: link["@_title"] || undefined,
            length: Number(link["@_length"] || 0),
        }));
        const acquisition = links.find((link) => link.rel.startsWith("http://opds-spec.org/acquisition"));
        return {
            id: text(entry.id),
            title: text(entry.title),
            content: entry.content ? {
                value: decodeContent(text(entry.content)),
                src: entry.content["@_src"] || undefined,
                type: entry.content["@_type"] || undefined,
            } : undefined,
            links,
            authors: list(entry.author).map((author) => ({
                id: text(author.uri).split("/").filter(Boolean).at(-1) || "",
                name: text(author.name),
            })),
            genres: genresFromLinks(links),
            series: seriesFromLinks(links),
            filesize: acquisition?.length ? String(Math.floor(acquisition.length / 1000)) : "",
            issued: text(entry["dcterms:issued"]),
            annotation: text(entry.summary),
            catType: text(
                categories.find(
                    (category) => category["@_scheme"] === "urn:sopds:catalog-type",
                )?.["@_term"],
            ),
        };
    });
    return {
        page: currentPage,
        pages: lastPage,
        entries,
        links: feedLinks,
    };
}

export async function fetchFeed(url) {
    const response = await fetch(url, {
        cache: "no-store",
        credentials: "same-origin",
        headers: {Accept: "application/atom+xml"},
    });
    if (!response.ok) throw new Error(`OPDS request failed: ${response.status}`);
    return parseFeed(await response.text());
}
