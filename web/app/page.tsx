import Link from "next/link";
import { Code } from "@/components/Code";
import { RoundingFigure } from "@/components/Figure";
import { Layers } from "@/components/Layers";
import { Stat } from "@/components/Stat";
import { n, wad } from "@/lib/format";
import { headline } from "@/lib/numbers";
import { moonwell, replay } from "@/lib/results";
import { FILM, REPO } from "@/lib/site";
import styles from "./home.module.css";

const FLOW = `pub trait Flow: Sealed {
    /// Rounding for bringing a given amount into internal accounting.
    type Admission: Rounding
    /// Rounding for turning an internal result into an amount to transfer.
    type Obligation: Rounding
    /// What the protocol gives in exchange moves the other way.
    type Opposite: Flow
}

/// Value the protocol pays out: count at least what leaves, pay no more than owed.
impl Flow for Out {
    type Admission = Ceil
    type Obligation = Floor
    type Opposite = In
}

pub fn admit<T, F: Flow>(_ q: Quantity<T, F, Given>, _ factor: ScalingFactor<T>) -> Quantity<
    T,
    F,
    Admitted,
> {
    Quantity { v: F::Admission::mul_div(q.v, factor.v, WAD) }
}`;

const REJECTED = `$ make show CASE=typed_pool_with_balancer_upscale
  the bug:   rejected by the compiler, error[8-0000]: type mismatch
             expected \`Quantity<_, Out, Admitted>\`, but \`u256\` is given
  the fix:   -    let scaled_out = upscale(amount_out.value(), factor.value())
             +    let scaled_out = admit(amount_out, factor)
  fixed:     compiles; PASS charges_what_the_typed_pool_charges_and_more_than_balancer`;

export default function Home() {
  const first = replay.attacks[0];
  const atMip = moonwell.prices.find((p) => p.block === moonwell.reference.mip_x43_block)!;
  return (
    <>
      <section className={styles.hero}>
        <div className={`wrap ${styles.heroGrid}`}>
          <div>
            <div className="eyebrow rise">A Fe library for financial arithmetic</div>
            <h1 className="rise" style={{ animationDelay: "0.05s" }}>
              Types that know which way <em>value&nbsp;moves.</em>
            </h1>
            <p className="lede rise" style={{ animationDelay: "0.12s" }}>
              In Dimension, the arithmetic behind two of DeFi&apos;s costliest recent failures does not compile. Each
              claim below is checked against the original code and the real chains, and every result on this site comes
              from a run you can repeat.
            </p>
            <div className={`rise ${styles.ctas}`} style={{ animationDelay: "0.18s" }}>
              <Link href="/verify" className="button">
                Verify every claim
              </Link>
              <a href={FILM} className="button ghost">
                ▶ Watch the film (2 min)
              </a>
              <Link href="/docs/guide" className="button ghost">
                Use the library
              </Link>
              <a href={REPO} className="button ghost">
                Source ↗
              </a>
            </div>
            <dl className={`rise ${styles.proof}`} style={{ animationDelay: "0.24s" }}>
              <div>
                <dt>{n(headline.vectors)}</dt>
                <dd>vectors against Balancer&apos;s Solidity, 0 mismatches</dd>
              </div>
              <div>
                <dt>
                  {headline.stepsEqual}/{headline.steps}
                </dt>
                <dd>real attack steps reproduced exactly</dd>
              </div>
              <div>
                <dt>
                  {headline.mutantsCaught}/{headline.mutants}
                </dt>
                <dd>planted bugs caught</dd>
              </div>
            </dl>
          </div>
          <div className="rise" style={{ animationDelay: "0.25s" }}>
            <RoundingFigure />
          </div>
        </div>
      </section>

      <section className="block">
        <div className="wrap">
          <blockquote className={styles.quote}>
            <p>
              “This is the only place where we round in the same direction for all amounts, as the impact of this
              rounding is expected to be minimal.”
            </p>
            <footer>
              Balancer V2, <code>_upscale</code>. In November 2025 that rounding drained its composable stable pools: 95 to
              128 million USD by various estimates.
            </footer>
          </blockquote>
          <p className={`lede ${styles.after}`}>
            The decision was written down, reviewed and shipped, because nothing could enforce it: to the compiler, every
            amount was a <code>u256</code>. Three months later a Moonwell governance proposal priced cbETH with its ETH
            exchange rate, in a feed named <code>cbETHETH_ORACLE</code>, and the market valued it at 1.12 USD for eight
            days. Dimension puts that meaning into the types.
          </p>
        </div>
      </section>

      <section className="block">
        <div className="wrap">
          <div className="eyebrow">Two incidents, replayed on their real code and chain state</div>
          <h2 style={{ margin: "14px 0 36px" }}>Reproduced exactly. Then stopped.</h2>
          <div className={styles.incidents}>
            <Link href="/balancer" className={`card ${styles.incident}`}>
              <div className={styles.tag}>Balancer V2 · 2025-11-03 · 95–128M USD</div>
              <div className={styles.big}>
                {headline.stepsEqual}
                <span>/{headline.steps}</span>
              </div>
              <p>
                of the attacker&apos;s real steps computed exactly as Balancer&apos;s Vault did, by the Fe port, from the
                real chain state. Every end state matches the pool&apos;s.
              </p>
              <div className={styles.split}>
                <div>
                  <b className="num">
                    {wad(first.faithful.value_per_bpt_start_wad, 4)} → {wad(first.faithful.value_per_bpt_end_wad, 4)}
                  </b>
                  <span>value per share, on Balancer&apos;s arithmetic</span>
                </div>
                <div>
                  <b className="num">step {first.typed.steps_completed}</b>
                  <span>where the attacker&apos;s own batch reverts on Dimension&apos;s typed kernel</span>
                </div>
              </div>
              <span className={styles.more}>The full replay →</span>
            </Link>
            <Link href="/moonwell" className={`card ${styles.incident}`}>
              <div className={styles.tag}>Moonwell MIP-X43 · 2026-02-15 · 1.78M USD bad debt</div>
              <div className={styles.big}>
                {wad(atMip.moonwell_wad, 2)}
                <span> vs {wad(atMip.fe_wad, 2)}</span>
              </div>
              <p>
                USD for one cbETH at block {n(moonwell.reference.mip_x43_block)}: Moonwell&apos;s deployed oracle, then
                Dimension&apos;s, reading the same two Chainlink feeds.
              </p>
              <div className={styles.split}>
                <div>
                  <b className="num">identical to the wei</b>
                  <span>where Moonwell was right, before MIP-X43 and after the fix</span>
                </div>
                <div>
                  <b className="num">rejected by the compiler</b>
                  <span>MIP-X43&apos;s configuration, written against the real Base feed registry</span>
                </div>
              </div>
              <span className={styles.more}>The on-chain record →</span>
            </Link>
          </div>
          <Link href="/vault" className={`card ${styles.third}`}>
            <span className={styles.tag}>Beyond the incidents · ERC-4626</span>
            <span>
              A vault that names no rounding agrees with OpenZeppelin&apos;s ERC4626 on{" "}
              <b className="num">{n(headline.vaultVectors)}</b> vectors. In {n(headline.vaultDecides)} of them, the
              direction decided the answer.
            </span>
            <span className={styles.more}>→</span>
          </Link>
        </div>
      </section>

      <section className="block">
        <div className="wrap">
          <div className="eyebrow">How it works</div>
          <h2 style={{ margin: "14px 0 12px" }}>Four layers. Each catches what the one before cannot.</h2>
          <p className="lede" style={{ marginBottom: 32 }}>
            Planting a bug in any of them is caught by the check meant for it. Breaking the type rule on purpose shows
            the layers are independent: the typed kernel then loses exactly as Balancer did, and the guard still rejects
            every loss.
          </p>
          <Layers />
        </div>
      </section>

      <section className="block">
        <div className="wrap">
          <div className="eyebrow">Checked and attacked</div>
          <h2 style={{ margin: "14px 0 32px" }}>Scale that answers a question.</h2>
          <div className={styles.stats}>
            <Stat value={n(headline.vectors)} label="vectors against Balancer's own Solidity, reverts included: 0 mismatches" run="make differential" />
            <Stat value={n(headline.quotes)} label="quotes against the deployed pool, the block before the attack: 0 mismatches" run="make fidelity" />
            <Stat value={`${headline.stepsEqual}/${headline.steps}`} label="of the real exploit's steps reproduced exactly; the typed kernels revert each batch" run="make replay" />
            <Stat value={`${(headline.operationsPerKernel / 1e6).toFixed(2)}M`} label={`operations per kernel over ${n(headline.states)} pool states, exact integers, both backends`} run="make explore" />
            <Stat value={`${headline.mutantsCaught}/${headline.mutants}`} label={`planted bugs caught by the check meant for each, across ${headline.mutantLayers} layers`} run="make mutants" />
            <Stat value={String(headline.compileFail)} label="constructions the compiler must reject, each with a corrected twin that passes" run="make compile-fail" />
            <Stat value={n(headline.vaultVectors)} label="ERC-4626 vectors equal to OpenZeppelin, no rounding named" run="make vault" />
            <Stat value={String(headline.moonwellBlocks)} label="Base blocks across MIP-X43: correct at every one" run="make moonwell" />
          </div>
        </div>
      </section>

      <section className="block">
        <div className={`wrap ${styles.fe}`}>
          <div>
            <div className="eyebrow">Fe highlight</div>
            <h2 style={{ margin: "14px 0 16px" }}>Rounding derived from meaning, at zero runtime cost.</h2>
            <p className="ink2">
              A direction is a sealed trait whose associated types name its roundings. Only <code>admit</code> produces
              an admitted amount, and it takes its rounding from the direction. A call site never names one, so it cannot
              name the wrong one. And the direction an amount is labelled with is checked against the money: a balance is
              credited only with value arriving, debited only with value leaving, and only ever by its own token.
            </p>
            <p className="ink2">
              The direction is resolved statically: on the library itself, the typed code compiles to the same bytes as
              hand-written <code>mul_div</code> calls at <code>-O1</code>, <code>-O2</code> and <code>-Os</code>. Effects make a feed
              read declare its calls and clock, and make failure a capability: one kernel reverts with Balancer&apos;s
              codes on the EVM and records failures in a native search.
            </p>
          </div>
          <div style={{ display: "grid", gap: 16, minWidth: 0 }}>
            <Code title="ingots/dimension/src/flow.fe, value.fe" lang="fe">
              {FLOW}
            </Code>
            <Code title="Balancer's line, put back into the typed pool" lang="shell" terminal>
              {REJECTED}
            </Code>
          </div>
        </div>
      </section>

      <section className="block">
        <div className={`wrap ${styles.fe}`}>
          <div>
            <div className="eyebrow">Use it in your protocol</div>
            <h2 style={{ margin: "14px 0 16px" }}>A Fe library. Five minutes to a typed contract.</h2>
            <p className="ink2">
              Dimension is an ingot, Fe&apos;s equivalent of a crate. <code>dimension new</code> creates a project from
              the quickstart, pinned to a release, and your contracts&apos; amounts, prices and policies are checked
              whenever they compile. <code>dimension check</code> runs the checklist before deploying: no{" "}
              <code>allow_unsafe</code>, no <code>unsafe</code> code, and every Chainlink feed the feed it claims to be.
            </p>
            <p className="ink2">
              CI runs both on every change: the new project must pass its tests, a misuse must be rejected, and the check
              must fail the project once it can forge what Dimension trusts.
            </p>
            <div className={styles.ctas}>
              <Link href="/docs/guide" className="button">
                Getting started
              </Link>
              <Link href="/docs/library" className="button ghost">
                The library
              </Link>
              <a href="/api/index.html" className="button ghost">
                API reference
              </a>
            </div>
          </div>
          <div style={{ display: "grid", gap: 16, minWidth: 0 }}>
            <Code title="fe.toml" lang="toml">
              {`[dependencies.dimension]
source = "https://github.com/Femtech-web/Dimension"
rev = "5a1aafe80e2f9034242fb6f5ada9b2495685d2ac"   # v0.3.1
name = "dimension"
version = "0.3.1"`}
            </Code>
            <Code title="with the command line" lang="shell">
              {`pipx install "git+https://github.com/Femtech-web/Dimension#subdirectory=cli"
dimension new my-protocol
(cd my-protocol && fe test)        # 3 tests, on the EVM
dimension check my-protocol --network base`}
            </Code>
          </div>
        </div>
      </section>

      <section className="block">
        <div className="wrap narrow">
          <div className="eyebrow">Don&apos;t take our word for it</div>
          <h2 style={{ margin: "14px 0 20px" }}>Every claim reproduces from one front door.</h2>
          <Code title="with only Docker: every offline check, no network" lang="shell">
            {`docker run --rm ghcr.io/femtech-web/dimension              # the published image
docker build -t dimension . && docker run --rm dimension   # or build it from a clone`}
          </Code>
          <p className="ink2" style={{ fontSize: 14.5, margin: "12px 0 22px" }}>
            Any other target runs the same way, such as{" "}
            <code>docker run --rm ghcr.io/femtech-web/dimension make demo</code>. Or with the toolchain:
          </p>
          <Code title="a clean clone" lang="shell">
            {`make toolchain   # Fe 26.6.0, downloaded and checksum-verified
make demo        # both incidents: the mistake, the verdict, the fix
make ci          # every offline check, about two and a half minutes
make replay      # the attacker's 360 steps, on mainnet forks
make mutants     # plant bugs; each must be caught`}
          </Code>
          <div className={styles.ctas} style={{ marginTop: 24 }}>
            <Link href="/verify" className="button">
              Every claim, with its evidence
            </Link>
            <Link href="/docs/judges" className="button ghost">
              The ten-minute tour
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
