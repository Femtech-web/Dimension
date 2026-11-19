import type { Claim } from "@/lib/results";

/** An icon and a word, never colour alone. */
export function Status({ holds, yes = "holds", no = "fails" }: { holds: boolean; yes?: string; no?: string }) {
  return holds ? (
    <span className="status good">
      <i aria-hidden="true">✓</i>
      {yes}
    </span>
  ) : (
    <span className="status bad">
      <i aria-hidden="true">✕</i>
      {no}
    </span>
  );
}

export function Claims({ claims }: { claims: Claim[] }) {
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }} className="card">
      {claims.map((c, i) => (
        <li
          key={i}
          style={{
            display: "grid",
            gridTemplateColumns: "84px 1fr",
            gap: 14,
            padding: "14px 18px",
            borderTop: i ? "1px solid var(--rule)" : 0,
          }}
        >
          <Status holds={c.holds} />
          <div>
            <div style={{ fontWeight: 500 }}>{c.question}</div>
            <div className="ink2" style={{ fontSize: 14.5, overflowWrap: "anywhere" }}>
              {c.evidence}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
