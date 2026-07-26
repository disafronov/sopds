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
      "Total: 36 items.",
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
  assert.equal(link.textContent, "Untitled Total: 6 books.");
  assert.equal(link.pathname, "/web/search/books/");
  assert.equal(
    link.search,
    "?searchtype=e&searchterms=__sopds_empty__",
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

test("book lists link each series by its stable id", async () => {
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

  const seriesLinks = [...window.document.querySelectorAll('a[href*="searchtype=s"]')];
  assert.deepEqual(
    seriesLinks.map((link) => link.textContent),
    ["Collection, with comma [3]", "Other collection"],
  );
  assert.deepEqual(
    seriesLinks.map((link) => new URL(link.href).searchParams.get("searchterms")),
    ["17", "23"],
  );
  const genreLinks = [...window.document.querySelectorAll('a[href*="searchtype=g"]')];
  assert.deepEqual(genreLinks.map((link) => link.textContent), ["sf", "sf_detective"]);
  assert.deepEqual(
    genreLinks.map((link) => new URL(link.href).searchParams.get("searchterms")),
    ["31", "32"],
  );
  assert.equal(window.document.body.textContent.includes("Hidden annotation"), false);
  assert.equal(window.document.body.textContent.includes("HTML must not be parsed"), false);
  assert.deepEqual(
    [...window.document.querySelectorAll("a.label.small")].map((link) => link.textContent),
    ["mobi", "fb2"],
  );
  assert.equal(
    window.document.querySelector(".book-card img.thumbnail").getAttribute("src"),
    "/opds/thumb/42/",
  );

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

test("footer book card hides structured XML annotation", async () => {
  const bookFeed = `<?xml version="1.0" encoding="utf-8"?>
  <feed xmlns="http://www.w3.org/2005/Atom" xmlns:sopds="urn:sopds:meta">
    <entry>
      <id>book:42</id>
      <title>Fixture book</title>
      <sopds:annotation>Hidden footer annotation</sopds:annotation>
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
