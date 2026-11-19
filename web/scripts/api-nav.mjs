#!/usr/bin/env node
// Finishes the API reference `fe doc` generates (web/public/api/index.html).
// It adds a way back to the site: a link pinned to the top-right corner, styled
// to match the reference's dark theme. And it points the reference's source
// links at this repository: `fe doc` names the Fe compiler's own repository.
// Run by `make apidoc` after generation.
import { readFileSync, writeFileSync } from "node:fs";

const page = new URL("../public/api/index.html", import.meta.url);
const MARK = 'id="dimension-home"';
const LINK =
  `<a ${MARK} href="/" style="position:fixed;top:10px;right:16px;z-index:2147483647;` +
  "display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;" +
  "background:#2b3040;color:#e4e8f4;border:1px solid #3d4457;font:500 13px/1.2 system-ui,-apple-system,sans-serif;" +
  'text-decoration:none;box-shadow:0 4px 14px rgba(0,0,0,.35)">&#8592; Dimension</a>';
const SOURCE = "https://github.com/Femtech-web/Dimension/blob/main";

let html = readFileSync(page, "utf8");
if (!html.includes(MARK)) {
  if (!html.includes("<body>")) throw new Error("no <body> in the generated API reference");
  html = html.replace("<body>", `<body>${LINK}`);
}
const base = /window\.FE_SOURCE_BASE = "[^"]*";/;
if (!base.test(html)) throw new Error("no FE_SOURCE_BASE in the generated API reference");
html = html.replace(base, `window.FE_SOURCE_BASE = "${SOURCE}";`);
writeFileSync(page, html);
console.log("api/index.html: link back to the site, and source links to this repository");
