import assert from "node:assert/strict";
import test from "node:test";

import {createOpdsClient, parseFeed} from "../js/opds.js";

const feed = `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <link href="/opds/search/books/a/test/?page=3" rel="self"/>
  <link href="/opds/search/books/a/test/?page=8" rel="last"/>
  <entry>
    <id>book:42</id><title>Test book</title>
    <content type="text/html">&lt;p&gt;Annotation &amp;amp; details&lt;/p&gt;</content>
    <link href="/opds/search/books/s/17/" rel="related" title="Series: Test series"/>
    <link href="/opds/search/books/g/31/" rel="related" title="Genre: Test genre"/>
    <category scheme="urn:sopds:catalog-type" term="2"/>
  </entry>
</feed>`;

test("OPDS parser is independent from browser globals", () => {
  const parsed = parseFeed(feed);

  assert.equal(parsed.entries[0].content.value, "<p>Annotation &amp; details</p>");
  assert.deepEqual(parsed.entries[0].links.slice(-2), [
    {href: "/opds/search/books/s/17/", rel: "related", type: undefined, title: "Series: Test series", length: 0},
    {href: "/opds/search/books/g/31/", rel: "related", type: undefined, title: "Genre: Test genre", length: 0},
  ]);
  assert.deepEqual(parsed.entries[0].categories, [{term: "2", scheme: "urn:sopds:catalog-type", label: undefined}]);
});

test("OPDS client receives its transport explicitly", async () => {
  const requests = [];
  const client = createOpdsClient({
    fetch: async (url, options) => {
      requests.push({url, options});
      return {ok: true, text: async () => feed};
    },
  });

  const parsed = await client.fetchFeed("/opds/search/books/a/test/?page=3");

  assert.equal(parsed.entries[0].title, "Test book");
  assert.deepEqual(requests, [{
    url: "/opds/search/books/a/test/?page=3",
    options: {
      cache: "no-store",
      credentials: "same-origin",
      headers: {Accept: "application/atom+xml"},
    },
  }]);
});
