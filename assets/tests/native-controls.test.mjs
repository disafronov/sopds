import assert from "node:assert/strict";
import { build } from "esbuild";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

async function loadFrontend(window) {
  const result = await build({
    entryPoints: [resolve(frontendRoot, "js/sopds.js")],
    bundle: true,
    format: "iife",
    write: false,
  });
  window.eval(result.outputFiles[0].text);
}

test("native controls preserve the web client interactions", async () => {
  const dom = new JSDOM(
    `<!doctype html>
      <html><body>
        <form id="searchform">
          <input id="main_searchbox" minlength="3" required>
          <input id="title" name="searchtype" type="radio" data-search-url="/web/search/books/" checked>
          <input id="author" name="searchtype" type="radio" data-search-url="/web/search/authors/">
          <button id="search-submit" type="submit">Search</button>
          <button class="search-dropdown-toggle" type="button" aria-controls="search-dropdown" aria-expanded="false">Toggle</button>
          <div id="search-dropdown" hidden></div>
        </form>
        <button class="menu-icon" type="button" aria-controls="main_menu" aria-expanded="false">Menu</button>
        <nav id="main_menu"><ul class="sopdsmenu">
          <li><button class="sopdsmenu__submenu-toggle" type="button" aria-expanded="false">Books</button><ul class="sopdsmenu__submenu"><li>One</li></ul></li>
          <li><button class="sopdsmenu__submenu-toggle" type="button" aria-expanded="false">Authors</button><ul class="sopdsmenu__submenu"><li>Two</li></ul></li>
        </ul></nav>
        <dialog id="DeleteBookModal" data-cover-url="/opds/cover/">
          <input id="DeleteBook_book">
          <img id="DeleteBook_image">
          <span id="DeleteBook_title"></span>
        </dialog>
        <button class="bookshelf-delete-trigger" data-book-id="42" data-book-title="Test book">Delete</button>
      </body></html>`,
    {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://sopds.test/web/",
    },
  );
  const { window } = dom;
  window.HTMLDialogElement.prototype.showModal = function showModal() {
    this.open = true;
  };
  window.HTMLDialogElement.prototype.close = function close() {
    this.open = false;
  };

  await loadFrontend(window);

  assert.equal(window.document.querySelector("#searchform").action, "https://sopds.test/web/search/books/");
  assert.equal(window.document.querySelector("#main_searchbox").placeholder, "Search by title");

  const searchBox = window.document.querySelector("#main_searchbox");
  assert.equal(searchBox.minLength, 3);
  searchBox.value = "abc";
  let searchSubmitted = false;
  window.document.querySelector("#searchform").addEventListener("submit", (event) => {
    event.preventDefault();
    searchSubmitted = true;
  });
  window.document.querySelector("#search-submit").click();
  assert.equal(searchSubmitted, true);

  const author = window.document.querySelector("#author");
  author.checked = true;
  author.dispatchEvent(new window.Event("change", { bubbles: true }));
  assert.equal(window.document.querySelector("#searchform").action, "https://sopds.test/web/search/authors/");
  assert.equal(window.document.querySelector("#main_searchbox").placeholder, "Search by author");

  const dropdownToggle = window.document.querySelector(".search-dropdown-toggle");
  dropdownToggle.click();
  assert.equal(window.document.querySelector("#search-dropdown").hidden, false);
  assert.equal(dropdownToggle.getAttribute("aria-expanded"), "true");

  window.document.querySelector(".menu-icon").click();
  assert.equal(window.document.querySelector("#main_menu").classList.contains("is-open"), true);
  assert.equal(window.document.querySelector("#search-dropdown").hidden, true);

  dropdownToggle.click();
  assert.equal(window.document.querySelector("#search-dropdown").hidden, false);
  assert.equal(window.document.querySelector("#main_menu").classList.contains("is-open"), false);

  window.document.body.click();
  assert.equal(window.document.querySelector("#search-dropdown").hidden, true);
  assert.equal(window.document.querySelector("#main_menu").classList.contains("is-open"), false);

  const [booksToggle, authorsToggle] = window.document.querySelectorAll(".sopdsmenu__submenu-toggle");
  booksToggle.click();
  assert.equal(booksToggle.closest("li").classList.contains("is-open"), true);
  authorsToggle.click();
  assert.equal(booksToggle.closest("li").classList.contains("is-open"), false);
  assert.equal(booksToggle.getAttribute("aria-expanded"), "false");
  assert.equal(authorsToggle.closest("li").classList.contains("is-open"), true);

  window.document.querySelector(".bookshelf-delete-trigger").click();
  assert.equal(window.document.querySelector("#DeleteBookModal").open, true);
  assert.equal(window.document.querySelector("#DeleteBook_book").value, "42");
  assert.equal(window.document.querySelector("#DeleteBook_image").src, "https://sopds.test/opds/cover/42/");
  assert.equal(window.document.querySelector("#DeleteBook_title").textContent, "Test book");

  window.document.querySelector("#DeleteBookModal").click();
  assert.equal(window.document.querySelector("#DeleteBookModal").open, false);

  dom.window.close();
});
