import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const vendorRoot = resolve(
  frontendRoot,
  "../../web_backend/static/js/vendor",
);

const assets = [
  ["jquery/dist/jquery.min.js", "jquery.min.js"],
  ["foundation-sites/dist/js/foundation.min.js", "foundation.min.js"],
  ["what-input/dist/what-input.min.js", "what-input.min.js"],
];

await mkdir(vendorRoot, { recursive: true });

await Promise.all(
  assets.map(([source, destination]) =>
    copyFile(
      resolve(frontendRoot, "node_modules", source),
      resolve(vendorRoot, destination),
    ),
  ),
);
