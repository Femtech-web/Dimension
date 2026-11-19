import styles from "./Layers.module.css";

const LAYERS = [
  {
    when: "Compile time",
    name: "Financial types",
    how: "Amounts carry token, direction and stage; prices carry their pair; policies carry predicates.",
    stops: "Balancer's _upscale in the typed pool. MIP-X43's feed in a USD slot.",
  },
  {
    when: "Deployment",
    name: "Bind check",
    how: "A contract's constructor checks each declared feed reports the declared decimals.",
    stops: "A registry that declares cbETH/ETH as an 8-decimal USD feed.",
  },
  {
    when: "Every read",
    name: "Read check",
    how: "Positive, fresh, inside the declared band: or the read reverts with a typed error.",
    stops: "A registry that declares cbETH/ETH as cbETH/USD with its real decimals.",
  },
  {
    when: "Every operation",
    name: "Runtime guard",
    how: "An exact 512-bit check that the value behind each pool share did not fall.",
    stops: "Losses from StableMath's own precision: 17 operations in 3.14 million.",
  },
];

export function Layers() {
  return (
    <div className={styles.layers}>
      {LAYERS.map((l, i) => (
        <div key={l.name} className={styles.layer} style={{ animationDelay: `${0.08 * i}s` }}>
          <div className={styles.when}>
            <span className="num">0{i + 1}</span> {l.when}
          </div>
          <h3>{l.name}</h3>
          <p>{l.how}</p>
          <div className={styles.stops}>
            <span>stops</span>
            {l.stops}
          </div>
        </div>
      ))}
      <div className={`${styles.layer} ${styles.rest}`}>
        <div className={styles.when}>What remains</div>
        <h3>A reviewed declaration</h3>
        <p>No check can prove an address is the feed it is declared to be. A wrong feed with the right decimals and a plausible answer passes.</p>
      </div>
    </div>
  );
}
