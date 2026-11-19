import Link from "next/link";

export default function NotFound() {
  return (
    <section style={{ padding: "96px 0" }}>
      <div className="wrap narrow">
        <div className="eyebrow">404</div>
        <h1 style={{ margin: "16px 0" }}>Nothing measured here.</h1>
        <p className="lede">
          <Link href="/">Back to the start</Link>, or <Link href="/judges">verify every claim</Link>.
        </p>
      </div>
    </section>
  );
}
