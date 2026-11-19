#!/usr/bin/env node
// Copies the saved results and the documentation into web/, so the site builds
// without the Fe toolchain and shows exactly what the runs produced:
// docs/results/<suite>/<platform>.json -> data/results/<suite>.json, and the
// markdown documentation -> content/. Run after `make ci` and the fork targets.
import { copyFileSync, existsSync, readdirSync, writeFileSync } from "node:fs";

const root = new URL("../../", import.meta.url);
const web = new URL("../", import.meta.url);
const PLATFORMS = ["linux_amd64", "mac_arm64"];

const results = new URL("docs/results/", root);
const suites = readdirSync(results, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name);
const platform = PLATFORMS.find((p) => suites.every((s) => existsSync(new URL(`${s}/${p}.json`, results))))
  ?? PLATFORMS.find((p) => suites.some((s) => existsSync(new URL(`${s}/${p}.json`, results))));
if (!platform) throw new Error("no saved results: run make ci first");

const copied = [];
for (const suite of suites) {
  const source = new URL(`${suite}/${platform}.json`, results);
  if (!existsSync(source)) continue;
  copyFileSync(source, new URL(`data/results/${suite}.json`, web));
  copied.push(suite);
}
writeFileSync(new URL("data/meta.json", web), JSON.stringify({ platform, suites: copied }, null, 2) + "\n");

const DOCS = {
  library: "ingots/dimension/README.md",
  judges: "JUDGES.md",
  guide: "docs/guide.md",
  balancer: "docs/balancer.md",
  moonwell: "docs/moonwell.md",
  vault: "docs/vault.md",
  architecture: "docs/architecture.md",
  guarantees: "docs/guarantees.md",
  comparison: "docs/comparison.md",
};
for (const [slug, path] of Object.entries(DOCS)) {
  copyFileSync(new URL(path, root), new URL(`content/${slug}.md`, web));
}
console.log(`results from ${platform}: ${copied.join(", ")}; ${Object.keys(DOCS).length} documents`);
