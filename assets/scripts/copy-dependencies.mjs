import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = resolve(frontendRoot, "../web_frontend/static/js");

const assets = [
  ["jquery/dist/jquery.min.js", "jquery.min.js"],
  ["jquery/dist/jquery.min.map", "jquery.min.map"],
  ["foundation-sites/dist/js/foundation.min.js", "foundation.min.js"],
  ["foundation-sites/dist/js/foundation.min.js.map", "foundation.min.js.map"],
  ["what-input/dist/what-input.min.js", "what-input.min.js"],
  ["what-input/dist/what-input.min.js.map", "what-input.min.js.map"],
];

await mkdir(outputRoot, { recursive: true });

await Promise.all(
  assets.map(([source, destination]) =>
    copyFile(
      resolve(frontendRoot, "node_modules", source),
      resolve(outputRoot, destination),
    ),
  ),
);
