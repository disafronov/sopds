import assert from "node:assert/strict";
import { build } from "esbuild";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

async function load(window, path) {
  window.eval(await readFile(resolve(frontendRoot, path), "utf8"));
}

async function loadFrontend(window) {
  const result = await build({
    entryPoints: [resolve(frontendRoot, "js/sopds.js")],
    bundle: true,
    format: "iife",
    write: false,
  });
  window.eval(result.outputFiles[0].text);
}

test("Foundation initializes with the pinned jQuery", async () => {
  const dom = new JSDOM(
    `<!doctype html>
      <html>
        <body>
          <form id="searchform">
            <input
              id="main_searchbox"
              minlength="3"
              required
            >
            <input
              id="title"
              name="searchtype"
              type="radio"
              data-search-url="/web/search/books/"
              checked
            >
            <input
              id="author"
              name="searchtype"
              type="radio"
              data-search-url="/web/search/authors/"
            >
            <button id="search-submit" type="submit">Search</button>
          </form>
          <form data-abide><input required></form>
          <button data-toggle="dropdown">Toggle</button>
          <div id="search-dropdown" data-dropdown></div>
          <div
            id="DeleteBookModal"
            data-reveal
            data-cover-url="/opds/cover/"
          >
            <input id="DeleteBook_book">
            <img id="DeleteBook_image">
            <span id="DeleteBook_title"></span>
          </div>
          <button
            class="bookshelf-delete-trigger"
            data-book-id="42"
            data-book-title="Test book"
          >
            Delete
          </button>
          <ul data-responsive-menu="accordion medium-dropdown" data-multi-open="false">
            <li>
              <a href="#">Books</a>
              <ul><li><a href="#">All books</a></li></ul>
            </li>
          </ul>
          <ul data-accordion-menu data-multi-open="false">
            <li>
              <a href="#">Authors</a>
              <ul><li><a href="#">All authors</a></li></ul>
            </li>
          </ul>
        </body>
      </html>`,
    {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://sopds.test/web/",
    },
  );
  const { window } = dom;

  window.matchMedia ??= () => ({
    addEventListener() {},
    matches: false,
    removeEventListener() {},
  });

  await load(window, "node_modules/jquery/dist/jquery.min.js");
  await load(window, "node_modules/what-input/dist/what-input.min.js");
  await load(window, "node_modules/foundation-sites/dist/js/foundation.min.js");
  await loadFrontend(window);

  assert.equal(window.jQuery.fn.jquery, "4.0.0");
  assert.equal(window.Foundation.version, "6.9.0");
  assert.equal(typeof window.whatInput.ask, "function");
  assert.equal(
    window.jQuery("[data-abide]").data("zfPlugin").className,
    "Abide",
  );
  assert.equal(
    window.jQuery("[data-dropdown]").data("zfPlugin").className,
    "Dropdown",
  );
  assert.equal(
    window.jQuery("[data-reveal]").data("zfPlugin").className,
    "Reveal",
  );
  assert.equal(
    window.jQuery("[data-responsive-menu]").data("zfPlugin").className,
    "ResponsiveMenu",
  );
  assert.equal(
    window.jQuery("[data-accordion-menu]").data("zfPlugin").options.multiOpen,
    false,
  );
  assert.equal(
    window.document.querySelector("#searchform").action,
    "https://sopds.test/web/search/books/",
  );
  assert.equal(
    window.document.querySelector("#main_searchbox").placeholder,
    "Search by title",
  );

  const searchBox = window.document.querySelector("#main_searchbox");
  assert.equal(searchBox.minLength, 3);
  searchBox.value = "abc";

  let searchSubmitted = false;
  window.document
    .querySelector("#searchform")
    .addEventListener("submit", (event) => {
      event.preventDefault();
      searchSubmitted = true;
    });
  window.document.querySelector("#search-submit").click();
  assert.equal(searchSubmitted, true);

  const author = window.document.querySelector("#author");
  author.checked = true;
  author.dispatchEvent(new window.Event("change", { bubbles: true }));
  assert.equal(
    window.document.querySelector("#searchform").action,
    "https://sopds.test/web/search/authors/",
  );

  let modalOpened = false;
  window.jQuery("[data-reveal]").data("zfPlugin").open = () => {
    modalOpened = true;
  };
  window.document.querySelector(".bookshelf-delete-trigger").click();
  assert.equal(modalOpened, true);
  assert.equal(window.document.querySelector("#DeleteBook_book").value, "42");
  assert.equal(
    window.document.querySelector("#DeleteBook_image").src,
    "https://sopds.test/opds/cover/42/",
  );
  assert.equal(
    window.document.querySelector("#DeleteBook_title").textContent,
    "Test book",
  );

  dom.window.close();
});
