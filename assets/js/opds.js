import { XMLParser } from "fast-xml-parser";

const parser = new XMLParser({
    ignoreAttributes: false,
    stopNodes: ["feed.entry.content"],
});

function list(value) {
    return value === undefined ? [] : Array.isArray(value) ? value : [value];
}

function text(value) {
    return typeof value === "object" && value !== null ? value["#text"] || "" : value || "";
}

function decodeContent(value) {
    const area = document.createElement("textarea");
    area.innerHTML = String(value).replace(/^<!\[CDATA\[|\]\]>$/gu, "");
    return area.value;
}

export function parseFeed(xml) {
    const feed = parser.parse(xml).feed || {};
    const entries = list(feed.entry).map((entry) => ({
        id: text(entry.id),
        title: text(entry.title),
        content: entry.content ? {value: decodeContent(text(entry.content))} : undefined,
        links: list(entry.link).map((link) => ({
            href: link["@_href"] || "",
            rel: link["@_rel"] || "",
            type: link["@_type"] || undefined,
        })),
        catType: Number(text(entry["sopds:cat-type"])),
        authors: list(entry.author).map((author) => text(author.name)),
        genres: list(entry.category).map((category) => category["@_term"] || category["@_label"] || ""),
    }));
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
