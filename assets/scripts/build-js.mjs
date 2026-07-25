import { build } from "esbuild";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = resolve(frontendRoot, "../web_frontend/static/js");

await mkdir(outputRoot, { recursive: true });
for (const name of ["sopds", "timezone"]) {
  await build({
    entryPoints: [resolve(frontendRoot, "js", `${name}.js`)],
    outfile: resolve(outputRoot, `${name}.min.js`),
    minify: true,
    bundle: name === "sopds",
    format: "iife",
    target: ["es2020"],
  });
}
