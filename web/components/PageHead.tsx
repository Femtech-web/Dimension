export function PageHead({ eyebrow, title, lede }: { eyebrow: string; title: React.ReactNode; lede: React.ReactNode }) {
  return (
    <section style={{ padding: "64px 0 44px" }}>
      <div className="wrap">
        <div className="eyebrow rise">{eyebrow}</div>
        <h1 className="rise" style={{ margin: "16px 0 20px", fontSize: "clamp(40px, 6vw, 72px)", animationDelay: "0.05s" }}>
          {title}
        </h1>
        <p className="lede rise" style={{ animationDelay: "0.1s" }}>
          {lede}
        </p>
      </div>
    </section>
  );
}

export function Section({ eyebrow, title, children }: { eyebrow?: string; title?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="block">
      <div className="wrap">
        {eyebrow && <div className={title ? "eyebrow" : "eyebrow solo"}>{eyebrow}</div>}
        {title && <h2 style={{ margin: "12px 0 24px", fontSize: "clamp(28px, 3.6vw, 42px)" }}>{title}</h2>}
        {children}
      </div>
    </section>
  );
}
