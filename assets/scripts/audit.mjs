import {spawnSync} from "node:child_process";

// xmlbuilder2 3.1.1 pins js-yaml 3.14.1. These advisories have no fixed
// version in the dependency chain used by opds-ts; keep the exception narrow
// so unrelated dependency vulnerabilities still fail the audit.
const ignoredAdvisories = new Set([
    "GHSA-mh29-5h37-fv8m",
    "GHSA-h67p-54hq-rp68",
    "GHSA-52cp-r559-cp3m",
]);

const result = spawnSync("npm", ["audit", "--json"], {
    encoding: "utf8",
});
const output = result.stdout || result.stderr || "";

let report;
try {
    report = JSON.parse(output);
} catch {
    process.stderr.write(output);
    process.exit(result.status ?? 1);
}

const vulnerabilities = report.vulnerabilities || {};
const resolving = new Set();

function advisoryId(item) {
    return item.url?.split("/").pop() || String(item.source);
}

function isIgnored(name) {
    if (resolving.has(name)) return false;
    const vulnerability = vulnerabilities[name];
    if (!vulnerability) return false;

    resolving.add(name);
    const ignored = (vulnerability.via || []).length > 0 && vulnerability.via.every((item) => {
        if (typeof item === "string") return isIgnored(item);
        return ignoredAdvisories.has(advisoryId(item));
    });
    resolving.delete(name);
    return ignored;
}

const remaining = Object.fromEntries(
    Object.entries(vulnerabilities).filter(([name]) => !isIgnored(name)),
);

if (Object.keys(remaining).length > 0) {
    process.stderr.write(`${JSON.stringify({...report, vulnerabilities: remaining}, null, 2)}\n`);
    process.exit(1);
}

process.stdout.write("npm audit: only documented no-fix opds-ts transitive advisories found\n");
