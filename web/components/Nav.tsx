"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV, REPO } from "@/lib/site";
import styles from "./Nav.module.css";

export function Nav() {
  const path = usePathname();
  return (
    <header className={styles.bar}>
      <div className={`wrap ${styles.inner}`}>
        <div className={styles.brand}>
          <Link href="/" className={styles.mark} aria-label="Dimension, home">
            <svg width="26" height="14" viewBox="0 0 26 14" aria-hidden="true">
              <path d="M1 1v12M25 1v12M1 7h24M5 4l-4 3 4 3M21 4l4 3-4 3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            </svg>
            <span>Dimension</span>
          </Link>
          <a href={`${REPO}/releases/tag/v0.1.0`} className={styles.version}>
            v0.1.0
          </a>
        </div>
        <nav className={styles.links} aria-label="Main">
          {NAV.map((item) =>
            item.file ? (
              <a key={item.href} href={item.href}>
                {item.label}
              </a>
            ) : (
              <Link key={item.href} href={item.href} aria-current={path.startsWith(item.href) ? "page" : undefined}>
                {item.label}
              </Link>
            ),
          )}
          <a href={REPO} className={styles.repo}>
            GitHub ↗
          </a>
        </nav>
      </div>
    </header>
  );
}
