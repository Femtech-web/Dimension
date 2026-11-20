import Link from "next/link";
import { differential } from "@/lib/results";
import { BUILD, RELEASE, REPO } from "@/lib/site";
import styles from "./Footer.module.css";

const COLUMNS: { title: string; links: [string, string][] }[] = [
  {
    title: "Evidence",
    links: [
      ["Balancer V2", "/balancer"],
      ["Moonwell MIP-X43", "/moonwell"],
      ["ERC-4626 vault", "/vault"],
      ["Live on Base Sepolia", "/live"],
      ["Verify every claim", "/verify"],
    ],
  },
  {
    title: "Library",
    links: [
      ["Getting started", "/docs/guide"],
      ["The library", "/docs/library"],
      ["API reference", "/api/index.html"],
      ["Changelog", `${REPO}/blob/main/CHANGELOG.md`],
    ],
  },
  {
    title: "Project",
    links: [
      ["Source", REPO],
      [`Release v${RELEASE.version}`, `${REPO}/releases/tag/v${RELEASE.version}`],
      ["Fe issue #2043", "https://github.com/argotorg/fe/issues/2043"],
      ["Security policy", `${REPO}/blob/main/SECURITY.md`],
    ],
  },
];

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={`wrap ${styles.grid}`}>
        <div className={styles.about}>
          <div className={styles.name}>Dimension</div>
          <p>Fe types that know which way value moves.</p>
          <p className={styles.meta}>
            Fe {differential.fe.version} ({differential.fe.commit.slice(0, 7)}). Every measured result on this site is
            rendered from a report in docs/results. Apache-2.0; the Balancer port is GPL-3.0-or-later.
          </p>
          {BUILD.commit && (
            <p className={styles.meta}>
              Built from commit{" "}
              <a href={`${REPO}/commit/${BUILD.commit}`} className="num">
                {BUILD.commit.slice(0, 7)}
              </a>
              {BUILD.dirty ? ", with changes not yet committed" : ""}.
            </p>
          )}
        </div>
        {COLUMNS.map((column) => (
          <nav key={column.title} aria-label={column.title}>
            <div className={styles.title}>{column.title}</div>
            {column.links.map(([label, href]) =>
              href.startsWith("/") && !href.endsWith(".html") ? (
                <Link key={label} href={href}>
                  {label}
                </Link>
              ) : (
                <a key={label} href={href}>
                  {label}
                </a>
              ),
            )}
          </nav>
        ))}
      </div>
    </footer>
  );
}
