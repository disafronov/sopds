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

export function parseFeed(xml) {
    const feed = parser.parse(xml).feed || {};
    const entries = list(feed.entry).map((entry) => {
        const links = list(entry.link).map((link) => ({
            href: link["@_href"] || "",
            rel: link["@_rel"] || "",
            type: link["@_type"] || undefined,
            length: Number(link["@_length"] || 0),
        }));
        const acquisition = links.find((link) => link.rel.startsWith("http://opds-spec.org/acquisition"));
        return {
            id: text(entry.id),
            title: text(entry.title),
            content: entry.content ? {value: decodeContent(text(entry.content))} : undefined,
            links,
            catType: Number(text(entry["sopds:cat-type"])),
            authors: list(entry.author).map((author) => ({
                id: text(author.uri).split("/").filter(Boolean).at(-1) || "",
                name: text(author.name),
            })),
            genres: list(entry.category).map((category) => ({
                id: category["@_sopds:id"] || "",
                name: category["@_term"] || category["@_label"] || "",
            })),
            series: list(entry["sopds:series"]).map((series) => ({
                id: series["@_id"] || "",
                name: text(series),
            })),
            filesize: acquisition?.length ? String(Math.floor(acquisition.length / 1000)) : "",
            issued: text(entry["dcterms:issued"]),
            annotation: text(entry.summary),
        };
    });
    return {
        page: Number(text(feed["sopds:page"]) || 1),
        pages: Number(text(feed["sopds:pages"]) || 1),
        entries,
        links: list(feed.link).map((link) => ({
            href: link["@_href"] || "",
            rel: link["@_rel"] || "",
            type: link["@_type"] || undefined,
            title: link["@_title"] || undefined,
        })),
    };
}

export async function fetchFeed(url) {
    const response = await fetch(url, {
        credentials: "same-origin",
        headers: {Accept: "application/atom+xml"},
    });
    if (!response.ok) throw new Error(`OPDS request failed: ${response.status}`);
    return parseFeed(await response.text());
}
