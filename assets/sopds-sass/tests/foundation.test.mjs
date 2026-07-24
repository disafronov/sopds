import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

async function load(window, path) {
  window.eval(await readFile(resolve(frontendRoot, path), "utf8"));
}

test("Foundation initializes with the pinned jQuery", async () => {
  const dom = new JSDOM(
    `<!doctype html>
      <html>
        <body>
          <form data-abide><input required></form>
          <button data-toggle="dropdown">Toggle</button>
          <div id="dropdown" data-dropdown></div>
          <div id="modal" data-reveal></div>
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

  window.jQuery(window.document).foundation();

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

  dom.window.close();
});
