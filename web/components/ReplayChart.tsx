"use client";

import { useMemo, useRef, useState } from "react";
import styles from "./Chart.module.css";

export type ReplayTx = {
  attack: number;
  block: number;
  start: number;
  faithful: number[];
  typed: number[];
  stop: number;
  reason: string;
  kinds: string[];
};

const W = 960;
const H = 390;
const M = { l: 62, r: 18, t: 40, b: 46 };
const GAP = 14;
const LOG_MIN = -6;
const LOG_MAX = Math.log10(2);

function fmt(v: number): string {
  if (v >= 0.01) return v.toFixed(4);
  return v.toExponential(2).replace("e-", "×10⁻").replace(/⁻(\d)$/, (_, d) => "⁻" + "⁰¹²³⁴⁵⁶⁷⁸⁹"[+d]);
}

export function ReplayChart({ txs }: { txs: ReplayTx[] }) {
  const total = txs.reduce((s, t) => s + t.faithful.length, 0) + GAP * (txs.length - 1);
  const plotW = W - M.l - M.r;
  const plotH = H - M.t - M.b;
  const y = (v: number) => M.t + plotH * (1 - (Math.log10(Math.max(v, 1e-7)) - LOG_MIN) / (LOG_MAX - LOG_MIN));

  const layout = useMemo(() => {
    let offset = 0;
    return txs.map((t) => {
      const x0 = offset;
      offset += t.faithful.length + GAP;
      const x = (step: number) => M.l + (plotW * (x0 + step)) / total;
      // Contiguous phases of the batch: exits, swaps at dust balances, joins.
      const phases: { kind: string; from: number; to: number }[] = [];
      t.kinds.forEach((k, i) => {
        const last = phases[phases.length - 1];
        if (last && last.kind === k) last.to = i + 1;
        else phases.push({ kind: k, from: i, to: i + 1 });
      });
      return { t, x, phases };
    });
  }, [txs, plotW, total]);

  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<{ tx: number; step: number } | null>(null);

  function locate(clientX: number) {
    const svg = svgRef.current;
    if (!svg) return;
    const box = svg.getBoundingClientRect();
    const vx = ((clientX - box.left) / box.width) * W;
    let best: { tx: number; step: number; d: number } | null = null;
    layout.forEach(({ t, x }, ti) => {
      for (let s = 0; s <= t.faithful.length; s++) {
        const d = Math.abs(x(s) - vx);
        if (!best || d < best.d) best = { tx: ti, step: s, d };
      }
    });
    if (best) setHover({ tx: (best as { tx: number }).tx, step: (best as { step: number }).step });
  }

  const ticks = [1, 0.1, 0.01, 1e-3, 1e-4, 1e-5, 1e-6];
  const h = hover ? layout[hover.tx] : null;
  const hv = (series: number[], start: number, step: number) => (step === 0 ? start : series[step - 1]);

  return (
    <figure className={styles.figure}>
      <figcaption className={styles.caption}>
        Value behind each pool share, after every step of the three attack transactions, replayed from the real chain
        state
      </figcaption>
      <div className={styles.legend}>
        <span>
          <i className={styles.keyBug} />
          Balancer V2 (the faithful Fe port: every step equal to the Vault)
        </span>
        <span>
          <i className={styles.keyDim} />
          Dimension&apos;s typed kernel
        </span>
      </div>
      <div className={styles.frame}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          tabIndex={0}
          aria-label="Value per share across the 360 attack steps. On Balancer's arithmetic it falls from 1.03 to 0.0000092. On the typed kernel it rises until the attacker's sequence reverts in each transaction. A table of the same values follows."
          onPointerMove={(e) => locate(e.clientX)}
          onPointerLeave={() => setHover(null)}
          onFocus={() => setHover({ tx: 0, step: 0 })}
          onBlur={() => setHover(null)}
          onKeyDown={(e) => {
            if (!hover) return;
            const t = layout[hover.tx].t;
            if (e.key === "ArrowRight") {
              setHover(hover.step < t.faithful.length ? { ...hover, step: hover.step + 1 } : hover.tx + 1 < layout.length ? { tx: hover.tx + 1, step: 0 } : hover);
              e.preventDefault();
            } else if (e.key === "ArrowLeft") {
              setHover(hover.step > 0 ? { ...hover, step: hover.step - 1 } : hover.tx > 0 ? { tx: hover.tx - 1, step: layout[hover.tx - 1].t.faithful.length } : hover);
              e.preventDefault();
            }
          }}
        >
          {layout.map(({ t, x, phases }) =>
            phases.map((p) => (
              <g key={`${t.attack}-${p.from}`}>
                {p.kind === "swap" && <rect x={x(p.from)} y={M.t} width={x(p.to) - x(p.from)} height={plotH} className={styles.band} />}
                {t.attack === 1 && (
                  <text x={(x(p.from) + x(p.to)) / 2} y={M.t - 8} textAnchor="middle" className={styles.phase}>
                    {p.kind === "exit" ? "exits" : p.kind === "swap" ? "swaps at dust" : "joins"}
                  </text>
                )}
              </g>
            )),
          )}
          {ticks.map((v) => (
            <g key={v}>
              <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} className={v === 1 ? styles.axis : styles.grid} />
              <text x={M.l - 8} y={y(v) + 4} textAnchor="end" className={styles.tick}>
                {v >= 0.01 ? v : `10⁻${"⁰¹²³⁴⁵⁶⁷⁸⁹"[-Math.log10(v)]}`}
              </text>
            </g>
          ))}
          {layout.map(({ t, x }) => (
            <g key={t.attack}>
              <text x={x(0)} y={H - 18} className={styles.tick}>
                transaction {t.attack} · block {t.block.toLocaleString("en-US")}
              </text>
              <polyline
                className={styles.lineBug}
                points={[t.start, ...t.faithful].map((v, s) => `${x(s).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}
              />
              <polyline
                className={styles.lineDim}
                points={[t.start, ...t.typed].map((v, s) => `${x(s).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}
              />
              <g transform={`translate(${x(t.stop + 1).toFixed(1)},${y(t.typed[t.typed.length - 1]).toFixed(1)})`} className={styles.revert}>
                <circle r={9} />
                <path d="M-4,-4 L4,4 M4,-4 L-4,4" />
              </g>
              {t.attack === 1 && (
                <text x={x(t.stop + 1) + 16} y={y(t.typed[t.typed.length - 1]) + 24} className={styles.note}>
                  the batch reverts at step {t.stop}: {t.reason}
                </text>
              )}
            </g>
          ))}
          {h && hover && <line x1={h.x(hover.step)} x2={h.x(hover.step)} y1={M.t} y2={H - M.b} className={styles.crosshair} />}
        </svg>
        {h && hover && (
          <div className={styles.tip} style={{ left: `${Math.min(80, (h.x(hover.step) / W) * 100 + 2)}%` }}>
            <div className={styles.tipHead}>
              Transaction {h.t.attack} · {hover.step === 0 ? "before the batch" : `after step ${hover.step - 1} (${h.t.kinds[hover.step - 1]})`}
            </div>
            <div className={styles.tipRow}>
              <i className={styles.keyBug} />
              <strong>{fmt(hv(h.t.faithful, h.t.start, hover.step))}</strong>
              <span>Balancer V2</span>
            </div>
            <div className={styles.tipRow}>
              <i className={styles.keyDim} />
              <strong>{hover.step <= h.t.typed.length ? fmt(hv(h.t.typed, h.t.start, hover.step)) : "reverted"}</strong>
              <span>{hover.step <= h.t.typed.length ? "Dimension" : `at step ${h.t.stop}, ${h.t.reason}`}</span>
            </div>
          </div>
        )}
      </div>
      <details className={styles.details}>
        <summary>The same values as a table</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Transaction</th>
                <th className="n">Steps</th>
                <th className="n">Balancer: value per share before → after</th>
                <th className="n">Typed: reverts at step</th>
                <th className="n">Typed: value per share before it stops</th>
              </tr>
            </thead>
            <tbody>
              {txs.map((t) => (
                <tr key={t.attack}>
                  <td>
                    {t.attack} · block {t.block.toLocaleString("en-US")}
                  </td>
                  <td className="n">{t.faithful.length}</td>
                  <td className="n">
                    {fmt(t.start)} → {fmt(t.faithful[t.faithful.length - 1])}
                  </td>
                  <td className="n">
                    {t.stop} ({t.reason})
                  </td>
                  <td className="n">{fmt(t.typed[t.typed.length - 1])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
