import assert from "node:assert/strict";
import { build } from "esbuild";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const COOKIE_ATTEMPT_KEY = "sopds-tz-cookie-attempt";

async function readTimezoneBundle() {
  const result = await build({
    entryPoints: [resolve(frontendRoot, "js/timezone.js")],
    bundle: true,
    format: "iife",
    write: false,
  });
  return result.outputFiles[0].text;
}

function createWindow() {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "https://sopds.test/web/",
  });
  return dom.window;
}

// In jsdom (29.x) `window.location.reload` is a LegacyUnforgeable own
// property, so it cannot be reassigned or redefined via
// `Object.defineProperty(window.location, "reload", ...)`. Instead, the
// bundle is evaluated inside a wrapper whose `location` parameter shadows
// the window global, letting us inject a counting stub without touching
// jsdom internals.
function loadTimezone(window, bundle) {
  const reloadCalls = { count: 0 };
  window.__tzReloadStub = () => {
    reloadCalls.count += 1;
  };
  const wrapped = `(function (location) { ${bundle} })({ reload: function () { window.__tzReloadStub(); } });`;
  window.eval(wrapped);
  return reloadCalls;
}

// Escape regex special characters so a timezone id (e.g. "Europe/Moscow")
// can be embedded into a RegExp pattern safely.
function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test("first visit sets the timezone cookie and reloads exactly once", async () => {
  const bundle = await readTimezoneBundle();
  const window = createWindow();

  const reloadCalls = loadTimezone(window, bundle);

  assert.equal(reloadCalls.count, 1);
  assert.match(window.document.cookie, /timezone=[^;]+/u);
  assert.equal(window.sessionStorage.getItem(COOKIE_ATTEMPT_KEY), "1");
});

test("re-running in the same session does not reload again", async () => {
  const bundle = await readTimezoneBundle();
  const window = createWindow();

  // Simulate the attempt flag left by a previous page load in this session
  // (e.g. when the cookie was blocked and never persisted).
  window.sessionStorage.setItem(COOKIE_ATTEMPT_KEY, "1");

  const reloadCalls = loadTimezone(window, bundle);

  assert.equal(reloadCalls.count, 0);
});

test("cookie stores the detected timezone value", async () => {
  const bundle = await readTimezoneBundle();
  const window = createWindow();

  loadTimezone(window, bundle);

  const tz = new window.Intl.DateTimeFormat().resolvedOptions().timeZone;
  assert.ok(tz, "jsdom window must report a timezone");
  assert.match(
    window.document.cookie,
    new RegExp(`(?:^|;\\s*)timezone=${escapeRegExp(tz)}(?:;|$)`, "u")
  );
});
