import { XMLParser } from "fast-xml-parser";

const parser = new XMLParser({
    ignoreAttributes: false,
    stopNodes: ["feed.entry.content"],
    trimValues: false,
    parseTagValue: false,
});
const contentParser = new XMLParser({
    ignoreAttributes: false,
    htmlEntities: true,
    trimValues: false,
    parseTagValue: false,
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
    return text(contentParser.parse(`<content>${String(value)}</content>`).content);
}

export function parseFeed(xml) {
    const feed = parser.parse(xml).feed || {};
    const feedLinks = list(feed.link).map((link) => ({
        href: link["@_href"] || "",
        rel: link["@_rel"] || "",
        type: link["@_type"] || undefined,
        title: link["@_title"] || undefined,
    }));
    const entries = list(feed.entry).map((entry) => {
        const categories = list(entry.category);
        const links = list(entry.link).map((link) => ({
            href: link["@_href"] || "",
            rel: link["@_rel"] || "",
            type: link["@_type"] || undefined,
            title: link["@_title"] || undefined,
            length: Number(link["@_length"] || 0),
        }));
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
                name: text(author.name),
                uri: text(author.uri) || undefined,
            })),
            categories: categories.map((category) => ({
                term: text(category["@_term"]),
                scheme: text(category["@_scheme"]) || undefined,
                label: text(category["@_label"]) || undefined,
            })),
            issued: text(entry["dcterms:issued"]),
            summary: text(entry.summary) || undefined,
        };
    });
    return {
        entries,
        links: feedLinks,
        title: text(feed.title),
    };
}

export function createOpdsClient({fetch: request}) {
    if (typeof request !== "function") {
        throw new TypeError("createOpdsClient requires a fetch implementation");
    }

    async function fetchFeed(url) {
        const response = await request(url, {
            cache: "no-store",
            credentials: "same-origin",
            headers: {Accept: "application/atom+xml"},
        });
        if (!response.ok) throw new Error(`OPDS request failed: ${response.status}`);
        return parseFeed(await response.text());
    }

    return {
        fetchFeed,
    };
}
