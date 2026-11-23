"use client";

import { useEffect, useRef, useState } from "react";
import { Status } from "@/components/Claims";
import { wad } from "@/lib/format";
import styles from "./Chart.module.css";
import own from "./BrowserKernels.module.css";

const KERNELS = ["faithful", "typed", "guarded"] as const;
type Kernel = (typeof KERNELS)[number];
type Run = { values: bigint[]; failure: number | null };

const W = 960;
const H = 340;
const M = { l: 62, r: 24, t: 24, b: 44 };
const NO_FAILURE = 0xffffffff;
// One exit every 120 ms plays the batch in about six seconds.
const STEP_MS = 120;

/** The batch through each kernel, by the module `make wasm` builds: the value
 * per BPT at the start and after each exit, up to the exit that fails. */
async function runAll(): Promise<{ count: number; runs: Record<Kernel, Run>; ms: number }> {
  const bytes = await (await fetch("/kernels.wasm")).arrayBuffer();
  const { instance } = await WebAssembly.instantiate(bytes, {});
  const { exits, value_after, failure } = instance.exports as {
    exits: () => number;
    value_after: (kernel: number, n: number) => bigint;
    failure: (kernel: number) => number;
  };
  const started = performance.now();
  const count = exits();
  const runs = {} as Record<Kernel, Run>;
  KERNELS.forEach((name, kernel) => {
    const values: bigint[] = [];
    for (let n = 0; n <= count; n++) {
      const v = BigInt.asUintN(64, value_after(kernel, n));
      if (v === 0n) break;
      values.push(v);
    }
    const code = failure(kernel) >>> 0;
    runs[name] = { values, failure: code === NO_FAILURE ? null : code };
  });
  return { count, runs, ms: performance.now() - started };
}

const asFloat = (v: bigint) => Number(v) / 1e18;
const bal = (code: number) => `BAL#${String(code).padStart(3, "0")}`;

export function BrowserKernels({ chain }: { chain: Record<Kernel, string> }) {
  const [result, setResult] = useState<Awaited<ReturnType<typeof runAll>> | null>(null);
  const [error, setError] = useState("");
  const [n, setN] = useState(0);
  const [playing, setPlaying] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const figureRef = useRef<HTMLElement>(null);

  useEffect(() => {
    runAll()
      .then((r) => {
        setResult(r);
        setN(r.count);
      })
      .catch(() => setError("This browser could not load the WebAssembly module."));
  }, []);

  // Plays the batch once from the start when the chart first comes into view,
  // unless the reader prefers reduced motion; until then it shows the outcome.
  useEffect(() => {
    const figure = figureRef.current;
    if (!result || !figure || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        setN(0);
        setPlaying(true);
      },
      { threshold: 0.5 },
    );
    observer.observe(figure);
    return () => observer.disconnect();
  }, [result]);

  useEffect(() => {
    if (!playing || !result) return;
    const timer = setInterval(() => setN((step) => Math.min(step + 1, result.count)), STEP_MS);
    return () => clearInterval(timer);
  }, [playing, result]);

  // The batch played to its last exit.
  useEffect(() => {
    if (playing && result && n >= result.count) setPlaying(false);
  }, [playing, result, n]);

  if (error) return <p className="ink2">{error}</p>;
  if (!result) return <p className="muted num">Running the kernels in WebAssembly…</p>;

  const { count, runs, ms } = result;
  const all = KERNELS.flatMap((k) => runs[k].values.map(asFloat));
  const lo = Math.floor((Math.min(...all) - 0.01) * 20) / 20;
  const hi = Math.ceil((Math.max(...all) + 0.01) * 20) / 20;
  const plotW = W - M.l - M.r;
  const plotH = H - M.t - M.b;
  const x = (step: number) => M.l + (plotW * step) / count;
  const y = (v: number) => M.t + plotH * (1 - (v - lo) / (hi - lo));
  const ticks = Array.from({ length: Math.round((hi - lo) / 0.05) + 1 }, (_, i) => +(lo + i * 0.05).toFixed(2));
  const line = (k: Kernel) => runs[k].values.map((v, i) => `${x(i).toFixed(1)},${y(asFloat(v)).toFixed(1)}`).join(" ");
  const typed = runs.typed;
  const stop = typed.values.length; // the exit that fails, counted from 1
  const equal = (k: Kernel) => runs[k].values.at(-1)?.toString() === chain[k];

  function toggle() {
    if (playing) setPlaying(false);
    else {
      if (n >= count) setN(0);
      setPlaying(true);
    }
  }

  function locate(clientX: number) {
    if (playing) return;
    const box = svgRef.current?.getBoundingClientRect();
    if (!box) return;
    const step = Math.round(((((clientX - box.left) / box.width) * W - M.l) / plotW) * count);
    setN(Math.max(0, Math.min(count, step)));
  }

  return (
    <figure className={styles.figure} ref={figureRef}>
      <figcaption className={styles.caption}>Value per BPT after each exit of the batch, computed in this browser</figcaption>
      <div className={styles.legend}>
        <span>
          <i className={styles.keyBug} />
          Balancer&apos;s arithmetic (faithful)
        </span>
        <span>
          <i className={styles.keyDim} />
          typed
        </span>
        <span>
          <i className={own.keyDashed} />
          guarded: the same values
        </span>
      </div>
      <div className={styles.frame}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          tabIndex={0}
          aria-label={`Over ${count} exits the faithful kernel's value per BPT falls from 1.0000 to ${wad(runs.faithful.values.at(-1)!, 4)}; the typed and guarded kernels' rises to ${wad(typed.values.at(-1)!, 4)}, then exit ${stop} fails with ${typed.failure === null ? "nothing" : bal(typed.failure)}. A table of the values follows.`}
          onPointerMove={(e) => locate(e.clientX)}
          onKeyDown={(e) => {
            setPlaying(false);
            if (e.key === "ArrowRight") setN(Math.min(count, n + 1));
            else if (e.key === "ArrowLeft") setN(Math.max(0, n - 1));
            else return;
            e.preventDefault();
          }}
        >
          {ticks.map((v) => (
            <g key={v}>
              <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} className={v === 1 ? styles.axis : styles.grid} />
              <text x={M.l - 8} y={y(v) + 4} textAnchor="end" className={styles.tick}>
                {v.toFixed(2)}
              </text>
            </g>
          ))}
          {[0, 10, 20, 30, 40, count].map((s) => (
            <text key={s} x={x(s)} y={H - 16} textAnchor="middle" className={styles.tick}>
              {s === 0 ? "start" : `exit ${s}`}
            </text>
          ))}
          <polyline className={styles.lineBug} points={line("faithful")} />
          <polyline className={styles.lineDim} points={line("typed")} />
          <polyline className={own.lineDashed} points={line("guarded")} />
          {typed.failure !== null && (
            <g className={styles.revert} transform={`translate(${x(stop)},${y(asFloat(typed.values.at(-1)!))})`}>
              <circle r={7} />
              <path d="M-3,-3L3,3M3,-3L-3,3" />
              <text x={-12} y={-12} textAnchor="end" className={styles.note}>
                exit {stop}: {bal(typed.failure)}
              </text>
            </g>
          )}
          <line x1={x(n)} x2={x(n)} y1={M.t} y2={H - M.b} className={styles.crosshair} />
        </svg>
      </div>

      <div className={own.controls}>
        <button type="button" className={`button ghost ${own.play}`} onClick={toggle} aria-label={playing ? "Pause the batch" : n >= count ? "Replay the batch from the start" : "Play the batch"}>
          <span aria-hidden="true">{playing ? "❚❚" : n >= count ? "↺" : "▶"}</span>
          {playing ? "Pause" : n >= count ? "Replay" : "Play"}
        </button>
        <label className={own.slider}>
          <span className="num">{n === 0 ? "At the start" : `After exit ${n} of ${count}`}</span>
          <input
            type="range"
            min={0}
            max={count}
            value={n}
            onChange={(e) => {
              setPlaying(false);
              setN(+e.target.value);
            }}
          />
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Kernel</th>
              <th className="n">Value per BPT</th>
              <th className="n">Since the start</th>
            </tr>
          </thead>
          <tbody>
            {KERNELS.map((k) => {
              const v = runs[k].values[n];
              const start = runs[k].values[0];
              return (
                <tr key={k}>
                  <td>{k}</td>
                  <td className="n">{v === undefined ? `exit ${runs[k].values.length}: ${bal(runs[k].failure!)}` : wad(v, 4)}</td>
                  <td className="n">
                    {v === undefined ? "reverted" : `${(((asFloat(v) - asFloat(start)) / asFloat(start)) * 100).toFixed(2)}%`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ul className={own.checks}>
        {KERNELS.map((k) => (
          <li key={k}>
            <Status holds={equal(k)} yes="equal" no="differs" />
            {k}, after {runs[k].values.length - 1} exits: {runs[k].values.at(-1)!.toString()}, to the wei the value the
            chain recorded
          </li>
        ))}
      </ul>
      <p className="muted" style={{ fontSize: 14 }}>
        Computed here in {ms.toFixed(0)} ms by Fe compiled to WebAssembly, from the same source as the deployed
        contracts. <code>make wasm</code> checks every step against the EVM, and <code>make native</code> does the same
        for these kernels built as a native library and called from C.
      </p>
      <details className={styles.details}>
        <summary>The same values as a table</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Exit</th>
                {KERNELS.map((k) => (
                  <th key={k} className="n">
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: count + 1 }, (_, i) => (
                <tr key={i}>
                  <td className="num">{i === 0 ? "start" : i}</td>
                  {KERNELS.map((k) => (
                    <td key={k} className="n">
                      {runs[k].values[i] === undefined
                        ? i === runs[k].values.length
                          ? bal(runs[k].failure!)
                          : ""
                        : wad(runs[k].values[i], 6)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
