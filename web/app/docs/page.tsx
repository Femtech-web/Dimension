import type { Metadata } from "next";
import Link from "next/link";
import { PageHead } from "@/components/PageHead";
import { DOCS } from "@/lib/docs";

export const metadata: Metadata = { title: "Documentation" };

export default function Docs() {
  return (
    <>
      <PageHead
        eyebrow="Documentation"
        title="Read the reasoning."
        lede="The same documents as the repository, rendered here. Links into the code go to the source on GitHub."
      />
      <section style={{ paddingBottom: 72 }}>
        <div className="wrap grid-2">
          {DOCS.map((d, i) => (
            <Link key={d.slug} href={`/docs/${d.slug}`} className="card" style={{ padding: "22px 24px", textDecoration: "none" }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>
                {String(i + 1).padStart(2, "0")}
              </div>
              <h3>{d.title}</h3>
              <p className="ink2" style={{ margin: "8px 0 0", fontSize: 15 }}>
                {d.blurb}
              </p>
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
