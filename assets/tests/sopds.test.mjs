import assert from "node:assert/strict";
import { build } from "esbuild";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

async function readClient() {
  const result = await build({
    entryPoints: [resolve(frontendRoot, "js/sopds.js")],
    bundle: true,
    format: "iife",
    write: false,
  });
  return result.outputFiles[0].text;
}

async function loadFrontend(window) {
  window.jQuery = () => ({foundation() {}});
  window.eval(await readClient());
}

const feed = `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>urn:test:feed</id>
  <title>Test feed</title>
  <entry>
    <id>prefix:A</id>
    <title>A</title>
    <link href="/opds/books/1/A/" rel="alternate"/>
    <link href="/opds/books/1/A/" rel="subsection"/>
    <content type="text">Found: 30 books</content>
  </entry>
  <entry>
    <id>prefix:AB</id>
    <title>AB</title>
    <link href="/opds/search/books/b/AB/" rel="alternate"/>
    <content type="text">Found: 2 books</content>
  </entry>
</feed>`;

test("OPDS selector preserves legacy web navigation", async () => {
  const dom = new JSDOM(
    `<!doctype html>
      <table
        data-opds-selector
        data-feed-url="/opds/books/1/"
        data-feed-kind="books"
        data-kind="book"
        data-lang-code="1"
        data-count-label="Total: %(count)s books."
        data-selector-url="/web/book/"
        data-search-url="/web/search/books/"
      >
        <tbody><tr data-opds-loading><td>Loading...</td></tr></tbody>
      </table>
      <p data-opds-error hidden>Unable to load the catalog.</p>`,
    {
      runScripts: "dangerously",
      url: "https://sopds.test/web/book/?lang=1",
    },
  );
  const { window } = dom;
  const requests = [];
  window.fetch = async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      text: async () => feed,
    };
  };

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/opds/books/1/");
  assert.equal(requests[0].options.credentials, "same-origin");

  const links = [...window.document.querySelectorAll(".selector-link")];
  assert.equal(links.length, 2);
  assert.equal(links[0].pathname, "/web/book/");
  assert.equal(links[0].search, "?lang=1&chars=A");
  assert.equal(links[1].pathname, "/web/search/books/");
  assert.equal(links[1].search, "?searchtype=b&searchterms=AB");
  assert.equal(
    links[0].querySelector(".selector-link__count").textContent,
    "Total: 30 books.",
  );
  assert.equal(
    links[1].querySelector(".selector-link__count").textContent,
    "Total: 2 books.",
  );

  dom.window.close();
});

test("genre adapter uses OPDS links and parent metadata", async () => {
  const genreFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom">
    <id>urn:test:feed</id>
    <title>Test feed</title>
    <link href="/opds/genres/" rel="up" title="Prose"/>
    <entry>
      <id>genre:42</id>
      <title>Contemporary prose</title>
      <link href="/opds/search/books/g/42/" rel="subsection"/>
      <content type="text">Found: 7 books</content>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <ul class="breadcrumbs"><li>Genres</li><li>Select</li></ul>
      <table
        data-opds-selector
        data-feed-url="/opds/genres/232/"
        data-mode="genre"
        data-count-label="Total: %(count)s books."
        data-selector-url="/web/genre/"
        data-search-url="/web/search/books/"
      ><tbody></tbody></table>
      <p data-opds-error hidden></p>`,
    {
      runScripts: "dangerously",
      url: "https://sopds.test/web/genre/?section=232",
    },
  );
  const { window } = dom;
  window.fetch = async () => ({
    ok: true,
    text: async () => genreFeed,
  });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const link = window.document.querySelector(".selector-link");
  assert.equal(link.pathname, "/web/search/books/");
  assert.equal(link.search, "?searchtype=g&searchterms=42");
  assert.deepEqual(
    [...window.document.querySelectorAll(".breadcrumbs li")].map(
      (item) => item.textContent,
    ),
    ["Genres", "Select", "Prose"],
  );

  dom.window.close();
});

test("entity adapter preserves result links and numeric pagination", async () => {
  const entityFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom" xmlns:sopds="urn:sopds:meta">
    <id>urn:test:feed</id>
    <title>Test feed</title>
    <sopds:page>2</sopds:page>
    <sopds:pages>5</sopds:pages>
    <entry>
      <id>a:42</id>
      <title>Test Author</title>
      <link href="/opds/search/books/as/42/" rel="subsection"/>
      <content type="text">Books count: 7</content>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <table
        data-opds-selector
        data-feed-url="/opds/search/authors/m/Test/2/"
        data-mode="entity"
        data-entity="author"
        data-count-label="Total: %(count)s books."
        data-search-url="/web/search/books/"
        data-page-url="/web/search/authors/"
        data-searchtype="m"
        data-searchterms="Test"
        data-half-pages="3"
      ><tbody></tbody></table>
      <div data-opds-pagination
           data-previous-label="Previous page"
           data-next-label="Next page"></div>
      <p data-opds-error hidden></p>`,
    {
      runScripts: "dangerously",
      url: "https://sopds.test/web/search/authors/?searchterms=Test&page=2",
    },
  );
  const { window } = dom;
  window.fetch = async () => ({
    ok: true,
    text: async () => entityFeed,
  });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const result = window.document.querySelector(".selector-link");
  assert.equal(result.pathname, "/web/search/books/");
  assert.equal(result.search, "?searchtype=a&searchterms=42");
  assert.equal(result.firstChild.textContent, "Test Author");
  assert.equal(
    result.querySelector(".selector-link__count").textContent,
    "Total: 7 books.",
  );

  const pagination = window.document.querySelector(".pagination");
  assert.equal(pagination.querySelector(".current").textContent, "2");
  assert.equal(
    pagination.querySelector(".pagination-previous a").search,
    "?searchtype=m&searchterms=Test&page=1",
  );
  assert.equal(
    pagination.querySelector(".pagination-next a").search,
    "?searchtype=m&searchterms=Test&page=3",
  );
  assert.deepEqual(
    [...pagination.querySelectorAll("li")].slice(1, -1).map(
      (item) => item.textContent,
    ),
    ["1", "2", "3", "4", "5"],
  );

  dom.window.close();
});

test("book lists hide annotations and preserve series commas", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom">
    <id>urn:test:feed</id>
    <title>Test feed</title>
    <entry>
      <id>book:42</id>
      <title>Fixture book</title>
      <author><name>Fixture author</name></author>
      <link href="/opds/search/books/i/42/" rel="alternate"/>
      <content type="text"><![CDATA[<b> Book name: </b>Fixture book<br/><b>Authors: </b>Fixture author<br/><b>Series: </b>Collection, with comma<br/><b>Genres: </b>prose_contemporary<br/><p class="book">Hidden annotation</p>]]></content>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <div data-opds-books data-feed-url="/opds/search/books/i/42/"></div>`,
    { runScripts: "dangerously", url: "https://sopds.test/web/search/books/" },
  );
  const { window } = dom;
  window.fetch = async () => ({ ok: true, text: async () => bookFeed });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const seriesLinks = [...window.document.querySelectorAll('a[href*="searchtype=s"]')];
  assert.equal(seriesLinks.length, 1);
  assert.equal(seriesLinks[0].textContent, "Collection, with comma");
  assert.equal(
    new URL(seriesLinks[0].href).searchParams.get("searchterms"),
    "Collection, with comma",
  );
  assert.equal(window.document.body.textContent.includes("Hidden annotation"), false);

  dom.window.close();
});

test("direct book page shows annotation", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom">
    <entry>
      <id>book:42</id>
      <title>Fixture book</title>
      <link href="/opds/search/books/i/42/" rel="alternate"/>
      <content type="text"><![CDATA[<b> Book name: </b>Fixture book<br/><p class="book">Visible annotation</p>]]></content>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <div data-opds-books data-searchtype="i" data-feed-url="/opds/search/books/i/42/"></div>`,
    { runScripts: "dangerously", url: "https://sopds.test/web/search/books/" },
  );
  const { window } = dom;
  window.fetch = async () => ({ ok: true, text: async () => bookFeed });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(window.document.body.textContent.includes("Visible annotation"), true);
  assert.ok(window.document.querySelector(".book-annotation"));
  dom.window.close();
});

test("footer book card hides annotation", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom">
    <entry>
      <id>book:42</id>
      <title>Fixture book</title>
      <content type="text"><![CDATA[<b> Book name: </b>Fixture book<br/><p class="book">Hidden footer annotation</p>]]></content>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <div data-opds-footer-book data-book-id="42"></div>`,
    { runScripts: "dangerously", url: "https://sopds.test/web/" },
  );
  const { window } = dom;
  window.fetch = async () => ({ ok: true, text: async () => bookFeed });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(window.document.body.textContent.includes("Hidden footer annotation"), false);
  dom.window.close();
});

test("direct book page omits empty annotation", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom">
    <entry>
      <id>book:42</id>
      <title>Fixture book</title>
      <content type="text"><![CDATA[<b> Book name: </b>Fixture book<br/><p class="book">  </p>]]></content>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <div data-opds-books data-searchtype="i" data-feed-url="/opds/search/books/i/42/"></div>`,
    { runScripts: "dangerously", url: "https://sopds.test/web/search/books/" },
  );
  const { window } = dom;
  window.fetch = async () => ({ ok: true, text: async () => bookFeed });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(window.document.querySelector(".book-annotation"), null);
  dom.window.close();
});
