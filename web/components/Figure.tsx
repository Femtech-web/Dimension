import styles from "./Figure.module.css";

/** The one-unit gap, drawn as a dimension: 17 wstETH leaving at rate 1.0581
 *  are 17.988 internal units. Balancer counted 17; Dimension counts 18. */
export function RoundingFigure() {
  const lo = 16.72;
  const hi = 18.28;
  const x = (v: number) => 24 + ((v - lo) / (hi - lo)) * 472;
  const exact = 17 * 1.058132408689971699;
  const axis = 150;
  return (
    <figure className={styles.figure}>
      <div className={styles.head}>17 wstETH leave the pool, at a rate of 1.0581</div>
      <svg
        viewBox="0 0 520 250"
        role="img"
        aria-label="17 wstETH leaving at rate 1.0581 are 17.988 internal units. Balancer V2 counted 17, leaving 0.988 uncounted; Dimension counts 18."
      >
        <line x1={x(lo)} x2={x(hi)} y1={axis} y2={axis} className={styles.axis} />
        {[17, 17.5, 18].map((v) => (
          <line key={v} x1={x(v)} x2={x(v)} y1={axis - (v % 1 ? 6 : 10)} y2={axis + (v % 1 ? 6 : 10)} className={styles.axis} />
        ))}
        <text x={x(17)} y={axis + 32} textAnchor="middle" className={styles.whole}>
          17
        </text>
        <text x={x(18)} y={axis + 32} textAnchor="middle" className={styles.whole}>
          18
        </text>

        <line x1={x(exact)} x2={x(exact)} y1={64} y2={axis} className={styles.exact} />
        <circle cx={x(exact)} cy={axis} r={5.5} className={styles.exactDot} />
        <text x={x(exact) - 10} y={56} textAnchor="end" className={styles.exactLabel}>
          17.988 units left the pool
        </text>

        <g className={styles.fix}>
          <path d={`M${x(exact)},100 H${x(18)} M${x(18)},92 v16`} />
          <text x={x(18) - 4} y={88} textAnchor="end">
            Dimension counts <tspan className={styles.strong}>18</tspan>
          </text>
        </g>

        <g className={styles.bug}>
          <path d={`M${x(17)},210 H${x(exact)}`} className={`${styles.dim} draw`} style={{ "--len": 330 } as React.CSSProperties} />
          <path d={`M${x(17)},202 v16 M${x(exact)},202 v16 M${x(17) + 10},205 l-10,5 l10,5 M${x(exact) - 10},205 l10,5 l-10,5`} />
          <text x={(x(17) + x(exact)) / 2} y={238} textAnchor="middle">
            Balancer V2 counted <tspan className={styles.strong}>17</tspan>: 0.988 of a unit uncounted
          </text>
        </g>
      </svg>
      <figcaption>
        An amount <b>leaving</b> the pool, scaled into internal units. Balancer V2 rounded every amount down, so the pool
        counted less than left it, on every exact-out swap and exit. In Dimension the direction comes from the type:{" "}
        <code>Out</code> rounds up, and the pool keeps the difference.
      </figcaption>
    </figure>
  );
}
