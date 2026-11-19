"use client";

import { useRef, useState } from "react";
import styles from "./Chart.module.css";

export type PricePoint = { block: number; ts: number; moonwell: number; fe: number; window: boolean };

const W = 960;
const H = 360;
const M = { l: 62, r: 18, t: 30, b: 42 };
const Y_MAX = 3000;

const usd = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const when = (ts: number) =>
  new Date(ts * 1000).toISOString().replace("T", " ").slice(5, 19).replace("-", "/") + " UTC";

export function PriceChart({ points }: { points: PricePoint[] }) {
  const t0 = points[0].ts - 36_000;
  const t1 = points[points.length - 1].ts + 36_000;
  const plotW = W - M.l - M.r;
  const plotH = H - M.t - M.b;
  const x = (ts: number) => M.l + (plotW * (ts - t0)) / (t1 - t0);
  const y = (v: number) => M.t + plotH * (1 - v / Y_MAX);
  const inWindow = points.filter((p) => p.window);
  const start = inWindow[0].ts;
  const end = points.find((p) => p.ts > inWindow[inWindow.length - 1].ts)!.ts;

  const days: number[] = [];
  for (let d = Math.ceil(t0 / 86400) * 86400; d < t1; d += 86400) days.push(d);

  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  function locate(clientX: number) {
    const box = svgRef.current!.getBoundingClientRect();
    const vx = ((clientX - box.left) / box.width) * W;
    let best = 0;
    points.forEach((p, i) => {
      if (Math.abs(x(p.ts) - vx) < Math.abs(x(points[best].ts) - vx)) best = i;
    });
    setHover(best);
  }
  const near = hover === null ? [] : points.filter((p) => Math.abs(x(p.ts) - x(points[hover].ts)) < 3);
  const mid = inWindow[Math.floor(inWindow.length / 2)].ts;
  const topFe = Math.max(...inWindow.map((p) => p.fe));

  return (
    <figure className={styles.figure}>
      <figcaption className={styles.caption}>cbETH price in USD at {points.length} Base blocks, from the same two Chainlink feeds</figcaption>
      <div className={styles.legend}>
        <span>
          <i className={styles.keyDim} />
          Dimension (<code>CbethUsdOracle</code>, deployed on each fork)
        </span>
        <span>
          <i className={styles.keyBug} />
          Moonwell&apos;s deployed oracle
        </span>
      </div>
      <div className={styles.frame}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          tabIndex={0}
          aria-label="Moonwell priced cbETH at about 1.12 USD throughout MIP-X43; Dimension priced it at 2,091 to 2,243 USD from the same feeds, and identically to Moonwell before and after. A table of the same values follows."
          onPointerMove={(e) => locate(e.clientX)}
          onPointerLeave={() => setHover(null)}
          onFocus={() => setHover(0)}
          onBlur={() => setHover(null)}
          onKeyDown={(e) => {
            if (hover === null) return;
            if (e.key === "ArrowRight") setHover(Math.min(points.length - 1, hover + 1));
            else if (e.key === "ArrowLeft") setHover(Math.max(0, hover - 1));
            else return;
            e.preventDefault();
          }}
        >
          <rect x={x(start)} y={M.t} width={x(end) - x(start)} height={plotH} className={styles.band} />
          <text x={x(start) + 8} y={M.t + 16} className={styles.phase}>
            MIP-X43 in effect
          </text>
          {[0, 500, 1000, 1500, 2000, 2500, 3000].map((v) => (
            <g key={v}>
              <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} className={v === 0 ? styles.axis : styles.grid} />
              <text x={M.l - 8} y={y(v) + 4} textAnchor="end" className={styles.tick}>
                {v === 0 ? "0" : v % 1000 === 0 ? `${v / 1000}K` : `${v / 1000}K`}
              </text>
            </g>
          ))}
          {days.map((d) => (
            <text key={d} x={x(d)} y={H - 16} textAnchor="middle" className={styles.tick}>
              {new Date(d * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })}
            </text>
          ))}
          <polyline className={styles.lineBug} points={points.map((p) => `${x(p.ts).toFixed(1)},${y(p.moonwell).toFixed(1)}`).join(" ")} />
          <polyline className={styles.lineDim} points={points.map((p) => `${x(p.ts).toFixed(1)},${y(p.fe).toFixed(1)}`).join(" ")} />
          {points.map((p) => (
            <g key={p.block}>
              <circle cx={x(p.ts)} cy={y(p.moonwell)} r={4} className={styles.mark} style={{ fill: "var(--bug)" }} />
              <circle cx={x(p.ts)} cy={y(p.fe)} r={4} className={styles.mark} style={{ fill: "var(--dim)" }} />
            </g>
          ))}
          <text x={x(mid)} y={y(topFe) - 14} textAnchor="middle" className={styles.note}>
            Dimension, same feeds
          </text>
          <text x={x(mid)} y={y(0) - 10} textAnchor="middle" className={styles.note}>
            Moonwell&apos;s oracle: about 1.12 USD
          </text>
          {hover !== null && <line x1={x(points[hover].ts)} x2={x(points[hover].ts)} y1={M.t} y2={H - M.b} className={styles.crosshair} />}
        </svg>
        {hover !== null && (
          <div className={styles.tip} style={{ left: `${Math.min(74, (x(points[hover].ts) / W) * 100 + 2)}%` }}>
            {near.map((p) => (
              <div key={p.block} style={{ marginBottom: 4 }}>
                <div className={styles.tipHead}>
                  Block {p.block.toLocaleString("en-US")} · {when(p.ts)}
                </div>
                <div className={styles.tipRow}>
                  <i className={styles.keyDim} />
                  <strong>{usd(p.fe)} USD</strong>
                  <span>Dimension</span>
                </div>
                <div className={styles.tipRow}>
                  <i className={styles.keyBug} />
                  <strong>{usd(p.moonwell)} USD</strong>
                  <span>Moonwell</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <details className={styles.details}>
        <summary>The same values as a table</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Block</th>
                <th>Time (UTC)</th>
                <th className="n">Moonwell (USD)</th>
                <th className="n">Dimension (USD)</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.block}>
                  <td className="num">{p.block.toLocaleString("en-US")}</td>
                  <td className="num">{when(p.ts)}</td>
                  <td className="n">{p.moonwell.toLocaleString("en-US", { maximumFractionDigits: 4 })}</td>
                  <td className="n">{p.fe.toLocaleString("en-US", { maximumFractionDigits: 4 })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
