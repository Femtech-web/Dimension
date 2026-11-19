export function Stat({ value, label, run }: { value: string; label: string; run?: string }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {run && <div className="stat-run">$ {run}</div>}
    </div>
  );
}
