import assert from "node:assert/strict";
import { build } from "esbuild";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

test("OPDS transport stays in the client module", async () => {
  const [client, frontend] = await Promise.all([
    readFile(resolve(frontendRoot, "js/opds.js"), "utf8"),
    readFile(resolve(frontendRoot, "js/sopds.js"), "utf8"),
  ]);

  assert.match(client, /export function createOpdsClient/u);
  assert.doesNotMatch(client, /\b(?:window|document)\b/u);
  assert.doesNotMatch(client, /new URL/u);
  assert.doesNotMatch(client, /text\/html/u);
  assert.match(frontend, /from "\.\/opds\.js"/u);
  assert.match(frontend, /fetch: \(\.\.\.args\) => window\.fetch\(\.\.\.args\)/u);
  assert.doesNotMatch(frontend, /XMLParser|DOMParser/u);
});

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
    "Found: 30 books",
  );
  assert.equal(
    links[1].querySelector(".selector-link__count").textContent,
    "Found: 2 books",
  );

  dom.window.close();
});

test("OPDS selector marks the current subsection without a self link", async () => {
  const dom = new JSDOM(
    `<!doctype html>
      <table
        data-opds-selector
        data-feed-url="/opds/books/1/"
        data-feed-kind="books"
        data-lang-code="1"
        data-selector-url="/web/book/"
        data-search-url="/web/search/books/"
      ><tbody></tbody></table>`,
    {
      runScripts: "dangerously",
      url: "https://sopds.test/web/book/?lang=1&chars=A",
    },
  );
  const {window} = dom;
  window.fetch = async () => ({ok: true, text: async () => feed});

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const selected = window.document.querySelector(".selector-link--current");
  assert.equal(selected.tagName, "SPAN");
  assert.equal(selected.getAttribute("aria-current"), "page");
  assert.equal(selected.hasAttribute("href"), false);
  assert.equal(window.document.querySelectorAll(".selector-link[href]").length, 1);

  dom.window.close();
});

test("OPDS selector keeps trailing spaces in subsection titles", async () => {
  const dom = new JSDOM(
    `<!doctype html>
      <table
        data-opds-selector
        data-feed-url="/opds/books/1/A/"
        data-feed-kind="books"
        data-lang-code="1"
        data-selector-url="/web/book/"
        data-search-url="/web/search/books/"
      ><tbody></tbody></table>`,
    {
      runScripts: "dangerously",
      url: "https://sopds.test/web/book/?lang=1&chars=A",
    },
  );
  const { window } = dom;
  window.fetch = async () => ({
    ok: true,
    text: async () => `<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>A</title><link href="/opds/search/books/e/A/" rel="subsection"/></entry>
      <entry><title>A </title><link href="/opds/books/1/A%20/" rel="subsection"/></entry>
      <entry><title>A"</title><link href="/opds/search/books/b/A%22/" rel="subsection"/></entry>
    </feed>`,
  });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const titles = [...window.document.querySelectorAll(".selector-link__title")];
  assert.deepEqual(titles.map((title) => title.textContent), ["A", "A ", "A\""]);
  assert.equal(
    window.document.querySelector(".selector-link").search,
    "?searchtype=e&searchterms=A",
  );

  dom.window.close();
});

test("OPDS selectors preserve zero as a digit", async () => {
  const digitFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom">
    <entry>
      <id>prefix:0</id>
      <title>0</title>
      <link href="/opds/search/items/b/0/" rel="alternate"/>
      <content type="text">Found: 36 items</content>
    </entry>
  </feed>`;
  for (const kind of ["book", "author", "series"]) {
    const dom = new JSDOM(
      `<!doctype html>
        <table
          data-opds-selector
          data-feed-url="/opds/${kind}/3/"
          data-feed-kind="${kind}"
          data-kind="${kind}"
          data-lang-code="3"
          data-count-label="Total: %(count)s items."
          data-selector-url="/web/${kind}/"
          data-search-url="/web/search/${kind}/"
        ><tbody></tbody></table>
        <p data-opds-error hidden></p>`,
      {
        runScripts: "dangerously",
        url: `https://sopds.test/web/${kind}/?lang=3`,
      },
    );
    const { window } = dom;
    window.fetch = async () => ({ok: true, text: async () => digitFeed});

    await loadFrontend(window);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

    const link = window.document.querySelector(".selector-link");
    assert.equal(link.firstChild.textContent, "0");
    assert.equal(link.pathname, `/web/search/${kind}/`);
    assert.equal(link.search, "?searchtype=b&searchterms=0");
    assert.equal(
      link.querySelector(".selector-link__count").textContent,
      "Found: 36 items",
    );

    dom.window.close();
  }
});

test("OPDS selector links empty-name placeholders to exact empty search", async () => {
  const emptyFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom">
    <entry>
      <id>/opds/search/books/e/__sopds_empty__/</id>
      <title>Untitled</title>
      <link href="/opds/search/books/e/__sopds_empty__/" rel="alternate"/>
      <content type="text">Found: 6 books</content>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <table
        data-opds-selector
        data-feed-url="/opds/books/9/"
        data-feed-kind="books"
        data-kind="book"
        data-lang-code="9"
        data-count-label="Total: %(count)s books."
        data-selector-url="/web/book/"
        data-search-url="/web/search/books/"
      ><tbody></tbody></table>
      <p data-opds-error hidden></p>`,
    {
      runScripts: "dangerously",
      url: "https://sopds.test/web/book/?lang=9",
    },
  );
  const { window } = dom;
  window.fetch = async () => ({ok: true, text: async () => emptyFeed});

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const link = window.document.querySelector(".selector-link");
  assert.equal(link.textContent, "Untitled Found: 6 books");
  assert.equal(link.pathname, "/web/search/books/");
  assert.equal(
    link.search,
    "?searchtype=e&searchterms=__sopds_empty__",
  );

  dom.window.close();
});

test("catalog icons follow Atom catalog-type categories", async () => {
  const catalogFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom">
    <entry>
      <id>c:1</id><title>Folder</title>
      <link href="/opds/catalogs/1/" rel="subsection"/>
      <category scheme="urn:sopds:catalog-type" term="0"/>
    </entry>
    <entry>
      <id>c:2</id><title>ZIP</title>
      <link href="/opds/catalogs/2/" rel="subsection"/>
      <category scheme="urn:sopds:catalog-type" term="1"/>
    </entry>
    <entry>
      <id>c:3</id><title>INPX</title>
      <link href="/opds/catalogs/3/" rel="subsection"/>
      <category scheme="urn:sopds:catalog-type" term="2"/>
    </entry>
    <entry>
      <id>c:4</id><title>INP</title>
      <link href="/opds/catalogs/4/" rel="subsection"/>
      <category scheme="urn:sopds:catalog-type" term="3"/>
    </entry>
    <entry>
      <id>c:5</id><title>Unknown</title>
      <link href="/opds/catalogs/5/" rel="subsection"/>
      <category scheme="urn:sopds:catalog-type" term="invalid"/>
    </entry>
    <entry>
      <id>c:6</id><title>Missing</title>
      <link href="/opds/catalogs/6/" rel="subsection"/>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <table class="clickable-rows" data-opds-catalogs
             data-feed-url="/opds/catalogs/" data-page-url="/web/catalogs/">
        <tbody></tbody>
      </table>`,
    { runScripts: "dangerously", url: "https://sopds.test/web/catalogs/" },
  );
  const { window } = dom;
  window.fetch = async () => ({ok: true, text: async () => catalogFeed});

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.deepEqual(
    [...window.document.querySelectorAll(".selector-link__icon")].map(
      (image) => image.getAttribute("src"),
    ),
    [
      "/static/images/folder.png",
      "/static/images/zip.png",
      "/static/images/inpx.png",
      "/static/images/inp.png",
      "/static/images/folder.png",
      "/static/images/folder.png",
    ],
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

test("entity adapter follows OPDS pagination links", async () => {
  const entityFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom" xmlns:sopds="urn:sopds:meta">
    <id>urn:test:feed</id>
    <title>Test feed</title>
    <link href="/opds/search/authors/m/Test/2/" rel="self"/>
    <link href="/opds/search/authors/m/Test/1/" rel="first"/>
    <link href="/opds/search/authors/m/Test/1/" rel="previous"/>
    <link href="/opds/search/authors/m/Test/3/" rel="next"/>
    <link href="/opds/search/authors/m/Test/5/" rel="last"/>
    <entry>
      <id>a:42</id>
      <title>Test Author</title>
      <link href="/opds/search/books/as/42/" rel="subsection"/>
      <content type="text">Books count: 7</content>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <div data-opds-pagination
           data-first-label="First"
           data-previous-label="Previous"
           data-next-label="Next"
           data-last-label="Last"></div>
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
           data-first-label="First"
           data-previous-label="Previous"
           data-next-label="Next"
           data-last-label="Last"></div>
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
    "Books count: 7",
  );

  const pagination = window.document.querySelector(".opds-pagination");
  assert.equal(window.document.querySelectorAll(".opds-pagination").length, 2);
  assert.equal(pagination.querySelector(".current").textContent, "2");
  assert.equal(pagination.querySelector(".pagination-first a").search, "?searchtype=m&searchterms=Test&page=1");
  assert.equal(pagination.querySelector(".pagination-first a").dataset.page, "1");
  assert.equal(pagination.querySelector(".pagination-first a").textContent, "1");
  assert.equal(pagination.querySelector(".pagination-first a").getAttribute("aria-label"), "First");
  assert.equal(pagination.querySelector(".pagination-previous"), null);
  assert.equal(
    pagination.querySelector(".pagination-next a").search,
    "?searchtype=m&searchterms=Test&page=3",
  );
  assert.equal(pagination.querySelector(".pagination-next a").dataset.page, "3");
  assert.equal(pagination.querySelector(".pagination-next a").textContent, "3");
  assert.equal(pagination.querySelector(".pagination-last a").search, "?searchtype=m&searchterms=Test&page=5");

  dom.window.close();
});

test("single-page OPDS feeds do not show pagination links", async () => {
  const dom = new JSDOM(
    `<!doctype html>
      <div data-opds-pagination
           data-first-label="First"
           data-previous-label="Previous"
           data-next-label="Next"
           data-last-label="Last"></div>
      <table data-opds-selector data-feed-url="/opds/search/books/u/0/">
        <tbody></tbody>
      </table>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/search/books/?searchtype=u"},
  );
  const {window} = dom;
  window.fetch = async () => ({
    ok: true,
    text: async () => `<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <link href="/opds/search/books/u/0/" rel="self"/>
      <link href="/opds/search/books/u/0/1/" rel="first"/>
      <link href="/opds/search/books/u/0/1/" rel="last"/>
    </feed>`,
  });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const pagination = window.document.querySelector("[data-opds-pagination]");
  assert.equal(pagination.hidden, true);
  assert.equal(pagination.children.length, 0);

  dom.window.close();
});

test("series adapter follows the OPDS subsection link instead of its entry id", async () => {
  const dom = new JSDOM(
    `<!doctype html><table
      data-opds-selector data-feed-url="/opds/search/series/m/Test/"
      data-mode="entity" data-entity="series" data-search-url="/web/search/books/"
    ><tbody></tbody></table>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/search/series/?searchterms=Test"},
  );
  const {window} = dom;
  window.fetch = async () => ({
    ok: true,
    text: async () => `<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <id>a:1263</id><title>Series</title>
      <link href="/opds/search/books/s/1263/" rel="subsection"/>
    </entry></feed>`,
  });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(
    window.document.querySelector(".selector-link").search,
    "?searchtype=s&searchterms=1263",
  );
  dom.window.close();
});

test("author-series OPDS links keep both identifiers", async () => {
  const dom = new JSDOM(
    `<!doctype html><table
      data-opds-selector data-feed-url="/opds/search/series/a/7/"
      data-mode="entity" data-entity="series" data-search-url="/web/search/books/"
    ><tbody></tbody></table>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/search/series/?searchterms=7"},
  );
  const {window} = dom;
  window.fetch = async () => ({
    ok: true,
    text: async () => `<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <id>a:9</id><title>Series</title>
      <link href="/opds/search/books/as/7/9/" rel="subsection"/>
    </entry></feed>`,
  });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(
    window.document.querySelector(".selector-link").search,
    "?searchtype=as&searchterms=7&searchterms0=9",
  );
  dom.window.close();
});

test("entity searches preserve digits, punctuation, and trailing spaces from OPDS links", async () => {
  const dom = new JSDOM(
    `<!doctype html><table
      data-opds-selector data-feed-url="/opds/search/authors/b/%23%20/"
      data-mode="entity" data-entity="author" data-search-url="/web/search/books/"
    ><tbody></tbody></table>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/search/authors/"},
  );
  const {window} = dom;
  window.fetch = async () => ({
    ok: true,
    text: async () => `<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title># </title><link href="/opds/search/authors/b/%23%20/" rel="subsection"/></entry>
      <entry><title>2024</title><link href="/opds/search/authors/e/2024/" rel="subsection"/></entry>
      <entry><title>C++</title><link href="/opds/search/series/b/C%2B%2B/" rel="subsection"/></entry>
      <entry><title>«</title><link href="/opds/search/series/b/%C2%AB/" rel="subsection"/></entry>
    </feed>`,
  });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const links = [...window.document.querySelectorAll(".selector-link")].map((link) => new URL(link.href));
  assert.deepEqual(
    links.map(({pathname, searchParams}) => [pathname, searchParams.get("searchtype"), searchParams.get("searchterms")]),
    [
      ["/web/search/authors/", "b", "# "],
      ["/web/search/authors/", "e", "2024"],
      ["/web/search/series/", "b", "C++"],
      ["/web/search/series/", "b", "«"],
    ],
  );
  dom.window.close();
});

test("book results are concise single-link navigation cards", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom" xmlns:sopds="urn:sopds:meta">
    <id>urn:test:feed</id>
    <title>Test feed</title>
    <entry>
      <id>book:42</id>
      <title>Fixture book</title>
      <author><name>Fixture author</name><uri>/opds/search/books/a/11/</uri></author>
      <link href="/opds/search/books/i/42/" rel="alternate"/>
      <link href="/opds/download/42/0/" rel="http://opds-spec.org/acquisition/open-access"
            type="application/x-mobipocket-ebook" length="12000"/>
      <link href="/opds/download/42/1/" rel="http://opds-spec.org/acquisition/open-access"
            type="application/fb2"/>
      <link href="/opds/thumb/42/" rel="http://opds-spec.org/image/thumbnail"
            type="image/jpeg"/>
      <category term="sf" label="sf"/>
      <category term="sf_detective" label="sf_detective"/>
      <link href="/opds/search/books/g/31/" rel="related"
            title="Genre: sf"
            type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
      <link href="/opds/search/books/g/32/" rel="related"
            title="Genre: sf_detective"
            type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
      <link href="/opds/search/books/s/17/" rel="related"
            title="Series: Collection, with comma [3]"
            type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
      <link href="/opds/search/books/s/23/" rel="related"
            title="Series: Other collection"
            type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
      <dcterms:issued xmlns:dcterms="http://purl.org/dc/terms">2026-07-26</dcterms:issued>
      <summary type="text">Hidden annotation</summary>
      <content type="text">HTML must not be parsed</content>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <div data-opds-books data-feed-url="/opds/search/books/i/42/"
           data-book-name-label="Book name" data-authors-label="Authors"
           data-series-label="Series" data-genres-label="Genres"
           data-file-size-label="File size"
           data-file-size-unit="KB" data-publication-date-label="Publication date"></div>`,
    { runScripts: "dangerously", url: "https://sopds.test/web/search/books/" },
  );
  const { window } = dom;
  window.fetch = async () => ({ ok: true, text: async () => bookFeed });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const card = window.document.querySelector("a.book-card");
  assert.equal(card.pathname, "/web/details/42/");
  assert.equal(card.querySelectorAll("a").length, 0);
  assert.equal(card.querySelector(".book-card__title").textContent, "Fixture book");
  assert.equal(card.querySelector(".book-card__authors").textContent, "Fixture author");
  assert.equal(card.querySelector(".book-card__genres").textContent, "sf, sf_detective");
  assert.equal(card.querySelector(".book-card__date").textContent, "2026-07-26");
  assert.equal(card.querySelectorAll(".book-card__metadata").length, 3);
  assert.equal(window.document.querySelectorAll(".book-card__actions").length, 0);
  assert.equal(window.document.body.textContent.includes("File size"), false);
  assert.equal(window.document.body.textContent.includes("Book name"), false);
  assert.equal(window.document.body.textContent.includes("Hidden annotation"), false);
  assert.equal(window.document.body.textContent.includes("HTML must not be parsed"), false);
  assert.equal(
    window.document.querySelector(".book-card img.book-card__image").getAttribute("src"),
    "/opds/thumb/42/",
  );

  dom.window.close();
});

test("book result falls back to a fixed empty cover and keeps metadata compact", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <id>book:99</id><title>Very long title that remains safely bounded in the card</title>
  </entry></feed>`;
  const dom = new JSDOM(
    `<!doctype html><div data-opds-books data-feed-url="/books/"
      data-authors-label="Authors" data-genres-label="Genres"
      data-publication-date-label="Publication date"></div>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/search/books/"},
  );
  const {window} = dom;
  window.fetch = async () => ({ok: true, text: async () => bookFeed});

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const card = window.document.querySelector("a.book-card");
  assert.equal(card.href, "https://sopds.test/web/details/99/");
  assert.equal(card.querySelector(".book-card__cover--empty") !== null, true);
  assert.equal(card.querySelectorAll(".book-card__metadata").length, 0);
  assert.equal(card.tabIndex, 0);
  assert.equal(card.matches("a"), true);

  dom.window.close();
});

test("bookshelf cards preserve downloads and delete controls outside navigation", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <id>book:42</id><title>Bookshelf book</title>
    <link href="/opds/download/42/0/" rel="http://opds-spec.org/acquisition/open-access" type="application/epub+zip"/>
  </entry></feed>`;
  const dom = new JSDOM(
    `<!doctype html><div data-opds-books data-feed-url="/books/" data-isbookshelf="1"
      data-download-label="Download" data-delete-label="Delete"></div>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/search/books/?searchtype=u"},
  );
  const {window} = dom;
  window.fetch = async () => ({ok: true, text: async () => bookFeed});

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(window.document.querySelector("a.book-card").pathname, "/web/details/42/");
  assert.equal(window.document.querySelectorAll("a.book-card a").length, 0);
  assert.equal(window.document.querySelector(".book-card__actions a").pathname, "/opds/download/42/0/");
  assert.equal(window.document.querySelector(".bookshelf-delete-trigger").textContent, "Delete");
  assert.equal(window.document.querySelectorAll(".book-card").length, 1);

  dom.window.close();
});

test("direct book page shows structured XML annotation", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom" xmlns:sopds="urn:sopds:meta">
    <entry>
      <id>book:42</id>
      <title>Fixture book</title>
      <link href="/opds/search/books/i/42/" rel="alternate"/>
      <summary type="text">Visible annotation</summary>
      <content type="text">Ignored HTML description</content>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html>
      <div data-opds-books data-searchtype="i" data-feed-url="/opds/search/books/i/42/"
           data-book-name-label="Book name" data-authors-label="Authors"
           data-series-label="Series" data-genres-label="Genres"
           data-file-size-label="File size"
           data-file-size-unit="KB" data-publication-date-label="Publication date"></div>`,
    { runScripts: "dangerously", url: "https://sopds.test/web/search/books/" },
  );
  const { window } = dom;
  window.fetch = async () => ({ ok: true, text: async () => bookFeed });

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(window.document.body.textContent.includes("Visible annotation"), true);
  assert.equal(window.document.body.textContent.includes("Ignored HTML description"), false);
  assert.ok(window.document.querySelector(".book-annotation"));
  dom.window.close();
});

test("book annotations respect the OPDS content type and sanitize HTML", async () => {
  const plainFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom"><entry><id>book:1</id><title>Plain</title>
    <content type="text">&lt;strong&gt;Literal text&lt;/strong&gt;</content>
  </entry></feed>`;
  const htmlFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom"><entry><id>book:2</id><title>HTML</title>
    <content type="text/html"><![CDATA[<p>Safe <strong>annotation</strong></p><img src="/cover.jpg" onerror="bad()"><a href="/reference">reference</a><a href="javascript:bad()">link</a><script>bad()</script>]]></content>
  </entry></feed>`;

  for (const [feedSource, plain] of [[plainFeed, true], [htmlFeed, false]]) {
    const dom = new JSDOM(
      `<!doctype html><div data-opds-book-detail data-feed-url="/detail/"
        data-annotation-label="Annotation"></div>`,
      {runScripts: "dangerously", url: "https://sopds.test/web/details/42/"},
    );
    const {window} = dom;
    window.fetch = async () => ({ok: true, text: async () => feedSource});

    await loadFrontend(window);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

    const annotation = window.document.querySelector(".book-detail-annotation");
    assert.ok(annotation);
    if (plain) {
      assert.equal(annotation.textContent.includes("<strong>Literal text</strong>"), true);
      assert.equal(annotation.querySelector("strong"), null);
    } else {
      assert.equal(annotation.querySelector("strong")?.textContent, "annotation");
      assert.equal(annotation.querySelector("img")?.getAttribute("src"), "/cover.jpg");
      assert.equal(annotation.querySelector("img")?.hasAttribute("onerror"), false);
      assert.equal(annotation.querySelector('a[href="/reference"]')?.textContent, "reference");
      assert.equal(annotation.querySelector('a[href^="javascript:"]'), null);
      assert.equal(annotation.querySelector("script"), null);
    }
    dom.window.close();
  }
});

test("direct book page omits empty structured XML annotation", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom" xmlns:sopds="urn:sopds:meta">
    <entry>
      <id>book:42</id>
      <title>Fixture book</title>
      <sopds:annotation>  </sopds:annotation>
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

test("book detail renders semantic metadata and acquisition links", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom" xmlns:dcterms="http://purl.org/dc/terms/">
    <entry>
      <id>book:42</id><title>Detail book</title>
      <author><name>Author Name</name><uri>/opds/search/books/a/11/</uri></author>
      <link href="/opds/download/42/0/" rel="http://opds-spec.org/acquisition/open-access"
            type="application/epub+zip" length="12000"/>
      <link href="/opds/download/42/1/" rel="http://opds-spec.org/acquisition/open-access"
            type="application/fb2" length="0"/>
      <link href="/opds/search/books/s/17/" rel="related" title="Series: Collection"/>
      <link href="/opds/search/books/g/31/" rel="related" title="Genre: sf"/>
      <dcterms:issued> </dcterms:issued>
    </entry>
  </feed>`;
  const dom = new JSDOM(
    `<!doctype html><div data-opds-book-detail data-feed-url="/detail/"
      data-cover-url="/opds/thumb/" data-no-cover="/static/no-cover.jpg"
      data-download-label="Download" data-cover-label="Book cover"
      data-authors-label="Authors" data-series-label="Series" data-genres-label="Genres"
      data-file-size-label="File size" data-file-size-unit="KB"
      data-publication-date-label="Date" data-annotation-label="Annotation"></div>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/details/42/"},
  );
  const {window} = dom;
  window.fetch = async () => ({ok: true, text: async () => bookFeed});

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(window.document.querySelectorAll("article.book-detail h1").length, 1);
  assert.equal(window.document.querySelector("article.book-detail h1").textContent, "Detail book");
  assert.equal(window.document.querySelector(".book-detail-cover").className.includes("medium-4"), true);
  assert.equal(window.document.querySelector(".book-detail-summary").className.includes("large-9"), true);
  assert.deepEqual(
    [...window.document.querySelectorAll(".book-detail-downloads a")].map((link) => [link.textContent, link.pathname]),
    [["epub", "/opds/download/42/0/"], ["fb2", "/opds/download/42/1/"]],
  );
  assert.equal(window.document.querySelectorAll(".book-detail-downloads a.button.small").length, 2);
  assert.equal(window.document.querySelectorAll(".book-detail-metadata dt").length, 4);
  assert.equal(window.document.body.textContent.includes("0 KB"), false);
  assert.equal(window.document.body.textContent.includes("Date"), false);
  assert.equal(window.document.querySelector(".book-detail-annotation"), null);
  assert.equal(window.document.body.textContent.includes("Annotation"), false);
  assert.equal(window.document.querySelector('a[href*="searchtype=a"]').search, "?searchtype=a&searchterms=11");
  assert.equal(window.document.querySelector('a[href*="searchtype=s"]').search, "?searchtype=s&searchterms=17");
  assert.equal(window.document.querySelector('a[href*="searchtype=g"]').search, "?searchtype=g&searchterms=31");

  dom.window.close();
});

test("book detail omits annotation section when all annotation sources are empty", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom"><entry><id>book:42</id><title>Empty book</title>
    <summary>  </summary>
    <content src="/annotation/42/" type="text/html"><![CDATA[  ]]></content>
  </entry></feed>`;
  const dom = new JSDOM(
    `<!doctype html><div data-opds-book-detail data-feed-url="/detail/"
      data-annotation-label="Annotation" data-loading-label="Loading"></div>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/details/42/"},
  );
  const {window} = dom;
  const requests = [];
  let resolveAnnotation;
  const annotationResponse = new Promise((resolvePromise) => {
    resolveAnnotation = resolvePromise;
  });
  window.fetch = async (url) => {
    requests.push(url);
    return requests.length === 1 ? {ok: true, text: async () => bookFeed} : annotationResponse;
  };

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
  assert.equal(window.document.querySelector(".book-detail-annotation-loading")?.textContent, "Loading");
  resolveAnnotation({ok: true, text: async () => "   "});
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.deepEqual(requests, ["/detail/", "/annotation/42/"]);
  assert.equal(window.document.querySelector(".book-detail-annotation"), null);
  assert.equal(window.document.body.textContent.includes("Annotation"), false);
  dom.window.close();
});

test("book detail treats empty DOM annotation content as absent", async () => {
  for (const [html, expectedText] of [
    ["<p></p>", ""],
    ["&nbsp;", ""],
    ["<p>Visible annotation</p>", "Visible annotation"],
  ]) {
    const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"><entry><id>book:42</id><title>Inline</title>
      <summary><![CDATA[${html}]]></summary>
    </entry></feed>`;
    const dom = new JSDOM(
      `<!doctype html><div data-opds-book-detail data-feed-url="/detail/"
        data-annotation-label="Annotation"></div>`,
      {runScripts: "dangerously", url: "https://sopds.test/web/details/42/"},
    );
    const {window} = dom;
    window.fetch = async () => ({ok: true, text: async () => bookFeed});

    await loadFrontend(window);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

    const section = window.document.querySelector(".book-detail-annotation");
    assert.equal(section?.textContent.replace("Annotation", "").trim() || "", expectedText);
    assert.equal(Boolean(section), Boolean(expectedText));
    dom.window.close();
  }
});

test("book detail applies DOM annotation check to lazy responses", async () => {
  for (const [html, expectedText] of [
    ["<p></p>", ""],
    ["&nbsp;", ""],
    ["<p>Visible annotation</p>", "Visible annotation"],
  ]) {
    const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"><entry><id>book:42</id><title>Lazy</title>
      <content src="/annotation/42/" type="text/html"/>
    </entry></feed>`;
    const dom = new JSDOM(
      `<!doctype html><div data-opds-book-detail data-feed-url="/detail/"
        data-annotation-label="Annotation" data-loading-label="Loading"></div>`,
      {runScripts: "dangerously", url: "https://sopds.test/web/details/42/"},
    );
    const {window} = dom;
    window.fetch = async (url) => url === "/detail/"
      ? {ok: true, text: async () => bookFeed}
      : {ok: true, text: async () => html};

    await loadFrontend(window);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

    const section = window.document.querySelector(".book-detail-annotation");
    assert.equal(section?.textContent.replace("Annotation", "").trim() || "", expectedText);
    assert.equal(Boolean(section), Boolean(expectedText));
    dom.window.close();
  }
});

test("book detail removes annotation section when lazy annotation fails", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom"><entry><id>book:42</id><title>Unavailable annotation</title>
    <content src="/annotation/42/" type="text/html"/>
  </entry></feed>`;
  const dom = new JSDOM(
    `<!doctype html><div data-opds-book-detail data-feed-url="/detail/"
      data-annotation-label="Annotation" data-loading-label="Loading"></div>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/details/42/"},
  );
  const {window} = dom;
  window.fetch = async (url) => url === "/detail/"
    ? {ok: true, text: async () => bookFeed}
    : Promise.reject(new Error("annotation unavailable"));

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(window.document.querySelector(".book-detail-annotation"), null);
  assert.equal(window.document.body.textContent.includes("Annotation"), false);
  dom.window.close();
});

test("book detail prefers inline annotation content before lazy source", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom"><entry><id>book:42</id><title>Annotated</title>
    <content src="/annotation/42/" type="text/html"><![CDATA[<p>Inline annotation</p>]]></content>
  </entry></feed>`;
  const dom = new JSDOM(
    `<!doctype html><div data-opds-book-detail data-feed-url="/detail/"
      data-cover-url="/opds/thumb/" data-no-cover="/static/no-cover.jpg"
      data-annotation-label="Annotation" data-loading-label="Loading"></div>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/details/42/"},
  );
  const {window} = dom;
  const requests = [];
  window.fetch = async (url) => {
    requests.push(url);
    return {ok: true, text: async () => bookFeed};
  };

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.equal(requests.length, 1);
  assert.equal(window.document.querySelector(".book-detail-annotation").textContent.includes("Inline annotation"), true);
  assert.equal(window.document.querySelector(".book-detail-annotation-loading"), null);
  dom.window.close();
});

test("book detail lazily loads annotation and falls back from a broken cover", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom"><entry><id>book:42</id><title>Lazy book</title>
    <content src="/annotation/42/" type="text/html"/>
  </entry></feed>`;
  const dom = new JSDOM(
    `<!doctype html><div data-opds-book-detail data-feed-url="/detail/"
      data-cover-url="/opds/thumb/" data-no-cover="/static/no-cover.jpg"
      data-annotation-label="Annotation" data-loading-label="Loading"></div>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/details/42/"},
  );
  const {window} = dom;
  const requests = [];
  window.fetch = async (url) => {
    requests.push(url);
    return requests.length === 1
      ? {ok: true, text: async () => bookFeed}
      : {ok: true, text: async () => "<p>Lazy annotation</p>"};
  };

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
  const image = window.document.querySelector(".book-detail-cover__image");
  image.dispatchEvent(new window.Event("error"));
  assert.equal(image.getAttribute("src"), "/static/no-cover.jpg");
  assert.equal(typeof image.onerror, "object");
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  assert.deepEqual(requests, ["/detail/", "/annotation/42/"]);
  assert.equal(window.document.querySelector(".book-detail-annotation").textContent.includes("Lazy annotation"), true);
  dom.window.close();
});

test("book detail keeps a visible localized error callout when feed fails", async () => {
  const dom = new JSDOM(
    `<!doctype html><div data-opds-book-detail data-feed-url="/detail/"
      data-loading-label="Loading" data-error-label="Book unavailable">
      <div data-opds-loading>Loading</div><div data-opds-error hidden role="alert">Book unavailable</div>
    </div>`,
    {runScripts: "dangerously", url: "https://sopds.test/web/details/42/"},
  );
  const {window} = dom;
  window.fetch = async () => ({ok: false, text: async () => ""});

  await loadFrontend(window);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

  const error = window.document.querySelector("[data-opds-error]");
  assert.equal(error.hidden, false);
  assert.equal(error.getAttribute("role"), "alert");
  assert.equal(error.textContent, "Book unavailable");
  assert.equal(window.document.querySelector("[data-opds-loading]").hidden, true);
  dom.window.close();
});
