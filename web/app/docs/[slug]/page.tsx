import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { DOCS, render } from "@/lib/docs";
import { BLOB } from "@/lib/site";
import styles from "./prose.module.css";

export function generateStaticParams() {
  return DOCS.map((d) => ({ slug: d.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  return { title: DOCS.find((d) => d.slug === slug)?.title ?? "Documentation" };
}

export default async function Doc({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const doc = render(slug);
  const meta = DOCS.find((d) => d.slug === slug);
  if (!doc || !meta) notFound();
  return (
    <div className={`wrap ${styles.layout}`}>
      <aside className={styles.side}>
        <div className="eyebrow">Documentation</div>
        <nav>
          {DOCS.map((d) => (
            <Link key={d.slug} href={`/docs/${d.slug}`} aria-current={d.slug === slug ? "page" : undefined}>
              {d.title}
            </Link>
          ))}
        </nav>
      </aside>
      <article className={styles.prose}>
        <h1>{doc.title}</h1>
        <div dangerouslySetInnerHTML={{ __html: doc.html }} />
        <p className={styles.source}>
          Source: <a href={`${BLOB}/${meta.source}`}>{meta.source}</a>
        </p>
      </article>
    </div>
  );
}
