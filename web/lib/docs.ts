import { readFileSync } from "node:fs";
import path from "node:path";
import { Marked, type Tokens } from "marked";
import { BLOB } from "./site";

/** The documents the site renders, synced into content/ by scripts/sync.mjs. */
export const DOCS = [
  { slug: "library", source: "ingots/dimension/README.md", title: "The library", blurb: "Install it, start from the quickstart, and what each module provides: the package page." },
  { slug: "judges", source: "JUDGES.md", title: "For judges", blurb: "Verify every claim in about ten minutes, and try to break it." },
  { slug: "balancer", source: "docs/balancer.md", title: "Balancer V2", blurb: "The flagship: ported, proven against the Solidity, the deployed pool and the attack itself, then typed." },
  { slug: "moonwell", source: "docs/moonwell.md", title: "Moonwell MIP-X43", blurb: "The on-chain record, block by block, and each layer that stops the mistake." },
  { slug: "vault", source: "docs/vault.md", title: "An ERC-4626 vault", blurb: "Four roundings derived from meaning, equal to OpenZeppelin's." },
  { slug: "guide", source: "docs/guide.md", title: "Using Dimension", blurb: "Getting started in five steps, each concept with tested code, and a checklist before production." },
  { slug: "interop", source: "docs/interop.md", title: "From other languages", blurb: "Solidity calls the contracts, JavaScript runs WebAssembly, C links a native library: the same integers, and what crosses each boundary." },
  { slug: "architecture", source: "docs/architecture.md", title: "Architecture", blurb: "The ingots, the type model, the boundaries and the verification design." },
  { slug: "guarantees", source: "docs/guarantees.md", title: "Guarantees", blurb: "What each layer guarantees, what it does not, residuals and costs." },
  { slug: "comparison", source: "docs/comparison.md", title: "Comparison", blurb: "Prior work, and exactly what Dimension adds to it." },
] as const;

const bySource = new Map<string, string>(DOCS.map((d) => [d.source, d.slug]));

function anchor(text: string): string {
  return text
    .toLowerCase()
    .replace(/<[^>]+>/g, "")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

/** Renders a document, keeping links between documents inside the site and
 *  sending links to code to the repository. */
export function render(slug: string): { title: string; html: string } | null {
  const doc = DOCS.find((d) => d.slug === slug);
  if (!doc) return null;
  const markdown = readFileSync(path.join(process.cwd(), "content", `${slug}.md`), "utf8");
  const base = path.posix.dirname(doc.source);
  const marked = new Marked({
    gfm: true,
    renderer: {
      link({ href, tokens }: Tokens.Link) {
        const text = this.parser.parseInline(tokens);
        let target = href;
        if (!/^(https?:|mailto:|#)/.test(href)) {
          const [file, hash] = href.split("#");
          const repoPath = path.posix.normalize(path.posix.join(base, file)).replace(/\/$/, "");
          const internal = bySource.get(repoPath);
          target = internal ? `/docs/${internal}${hash ? `#${hash}` : ""}` : `${BLOB}/${repoPath}${hash ? `#${hash}` : ""}`;
        }
        const external = /^https?:/.test(target);
        return `<a href="${target}"${external ? ' rel="noopener"' : ""}>${text}</a>`;
      },
      heading({ tokens, depth }: Tokens.Heading) {
        const text = this.parser.parseInline(tokens);
        return `<h${depth} id="${anchor(text)}">${text}</h${depth}>\n`;
      },
    },
  });
  const title = markdown.match(/^# (.+)$/m)?.[1] ?? doc.title;
  const body = markdown.replace(/^# .+\n/, "");
  return { title, html: marked.parse(body, { async: false }) as string };
}
