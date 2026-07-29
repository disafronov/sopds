import { XMLParser } from "fast-xml-parser";

const parser = new XMLParser({
    ignoreAttributes: false,
    stopNodes: ["feed.entry.content"],
});
const contentParser = new XMLParser({
    ignoreAttributes: false,
    htmlEntities: true,
});
const defaultBaseUrl = "http://opds.invalid/";

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
    return text(contentParser.parse(`<content>${String(value)}</content>`).content);
}

function linkPath(href, baseUrl) {
    return new URL(href, baseUrl).pathname.split("/").filter(Boolean);
}

function pageNumber(href, baseUrl) {
    if (!href) return 0;
    const url = new URL(href, baseUrl);
    const queryPage = Number(url.searchParams.get("page"));
    if (queryPage > 0) return queryPage;
    const finalSegment = linkPath(href, baseUrl).at(-1);
    return /^\d+$/u.test(finalSegment || "") ? Number(finalSegment) : 1;
}

function entitiesFromLinks(links, kind, baseUrl) {
    return links
        .filter((link) => {
            if (link.rel !== "related") return false;
            return linkPath(link.href, baseUrl).at(-2) === kind;
        })
        .map((link) => ({
            id: linkPath(link.href, baseUrl).at(-1) || "",
            name: (link.title || "").replace(/^[^:]+:\s*/u, ""),
        }));
}

export function parseFeed(xml, {baseUrl = defaultBaseUrl} = {}) {
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
    const previousPage = pageNumber(linkByRel("previous", "prev")?.href, baseUrl);
    const nextPage = pageNumber(linkByRel("next")?.href, baseUrl);
    const currentPage = previousPage
        ? previousPage + 1
        : nextPage
            ? Math.max(1, nextPage - 1)
            : pageNumber(linkByRel("self")?.href, baseUrl) || 1;
    const lastPage = pageNumber(linkByRel("last")?.href, baseUrl) || currentPage;
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
            genres: entitiesFromLinks(links, "g", baseUrl),
            series: entitiesFromLinks(links, "s", baseUrl),
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

export function createOpdsClient({fetch: request, baseUrl = defaultBaseUrl}) {
    if (typeof request !== "function") {
        throw new TypeError("createOpdsClient requires a fetch implementation");
    }

    async function fetchResource(url, accept) {
        const response = await request(url, {
            cache: "no-store",
            credentials: "same-origin",
            headers: {Accept: accept},
        });
        if (!response.ok) throw new Error(`OPDS request failed: ${response.status}`);
        return {
            text: await response.text(),
            url: response.url || new URL(url, baseUrl).href,
        };
    }

    return {
        async fetchFeed(url) {
            const response = await fetchResource(url, "application/atom+xml");
            return parseFeed(response.text, {baseUrl: response.url});
        },
        async fetchLinkedContent(url) {
            return (await fetchResource(url, "text/html")).text;
        },
    };
}
