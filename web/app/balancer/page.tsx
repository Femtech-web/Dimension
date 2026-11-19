import type { Metadata } from "next";
import Link from "next/link";
import { Claims } from "@/components/Claims";
import { Code } from "@/components/Code";
import { PageHead, Section } from "@/components/PageHead";
import { ReplayChart } from "@/components/ReplayChart";
import { Stat } from "@/components/Stat";
import { n, pct, wad } from "@/lib/format";
import { gas, headline, replayTxs, search } from "@/lib/numbers";
import { differential, evm, exploration, fidelity, replay } from "@/lib/results";
import { BLOB } from "@/lib/site";

export const metadata: Metadata = { title: "Balancer V2" };

const UPSCALE = `function _upscale(uint256 amount, uint256 scalingFactor) pure returns (uint256) {
    // Upscale rounding wouldn't necessarily always go in the same direction: in a swap for example the balance of
    // token in should be rounded up, and that of token out rounded down. This is the only place where we round in
    // the same direction for all amounts, as the impact of this rounding is expected to be minimal.
    return FixedPoint.mulDown(amount, scalingFactor);
}`;

const REJECTED = `$ make show CASE=typed_pool_with_balancer_upscale
  the bug:   rejected by the compiler, error[8-0000]: type mismatch
             expected \`Quantity<_, Out, Admitted>\`, but \`u256\` is given
  the fix:   -    let scaled_out = upscale(amount_out.value(), factor.value())
             +    let scaled_out = admit(amount_out, factor)
  fixed:     compiles; PASS charges_what_the_typed_pool_charges_and_more_than_balancer`;

const rel = (v: number, base: number) => pct(((v - base) / base) * 100, 1);

export default function Balancer() {
  const rows = search();
  const gasRows = gas();
  const levels = evm.runtime_bytecode_bytes_by_level as Record<string, Record<string, number>>;
  return (
    <>
      <PageHead
        eyebrow="Balancer V2 · composable stable pools · 2025-11-03"
        title={
          <>
            Reproduced to the wei. <em>Then made unwritable.</em>
          </>
        }
        lede={
          <>
            The attacker drained the osETH/wETH pool in three transactions. Dimension&apos;s Fe port of Balancer runs
            every one of their {headline.steps} steps from the real chain state and computes exactly what Balancer&apos;s
            Vault computed. The same steps on Dimension&apos;s typed kernel pay the pool, until the attacker&apos;s batch
            reverts.
          </>
        }
      />

      <Section eyebrow="The attack, replayed" title="Every step of the real exploit, on both arithmetics.">
        <ReplayChart txs={replayTxs()} />
        <p className="ink2" style={{ marginTop: 18 }}>
          Fixtures are the swaps Balancer&apos;s Vault executed on this pool, read from each transaction&apos;s events.
          Each transaction is replayed on a mainnet fork at that transaction. The faithful kernel must compute every
          amount Balancer computed, and must end in the pool&apos;s real state once the real transaction runs on the same
          fork. The typed kernel charges more once balances reach dust, and the attacker&apos;s plan stops fitting the
          pool: step {replay.attacks[0].typed.steps_completed} (counting from 0) fails Balancer&apos;s own <code>BAL#001</code> check.
        </p>
        <p className="ink2">
          What this shows, and what it does not: the attacker&apos;s own sequence cannot run against the typed kernels.
          An attacker who knew the pool rounds correctly would search for another; the exhaustive search and the greedy
          attacker below are the evidence that none pays.
        </p>
        <div style={{ marginTop: 24 }}>
          <Claims claims={replay.claims} />
        </div>
      </Section>

      <Section eyebrow="The port is Balancer" title="Three independent proofs, before any type is applied.">
        <div className="grid-3">
          <Stat
            value={`${n(differential.summary.vectors)}`}
            label={`vectors against Balancer's own Solidity (solc 0.7.6), on identical calldata: ${differential.summary.mismatches} mismatches, ${n(differential.summary.both_reverted)} identical reverts`}
            run="make differential"
          />
          <Stat
            value={n(fidelity.summary.compared)}
            label={`quotes against the deployed pool at block ${n(fidelity.reference.block)}, the last before the attack, for amounts up to a fifth of its 4,922 WETH: ${fidelity.summary.mismatches} mismatches`}
            run="make fidelity"
          />
          <Stat
            value={`${headline.stepsEqual}/${headline.steps}`}
            label="attack steps computed exactly as the Vault did, and every end state equal to the real pool's"
            run="make replay"
          />
        </div>
        <p className="ink2" style={{ marginTop: 22 }}>
          The port covers FixedPoint, Math and StableMath line by line, the composable stable pool&apos;s swap, join and
          exit paths, and the protocol fees it mints on every join and exit. Without the fees the replay could not match:
          the pool minted fee shares 33 times in the first attack transaction alone.
        </p>
      </Section>

      <Section eyebrow="The line" title="Written down, reviewed, shipped.">
        <div className="grid-2">
          <Code title="pkg/solidity-utils/contracts/helpers/ScalingHelpers.sol" lang="solidity">
            {UPSCALE}
          </Code>
          <Code title="the same line, put back into Dimension's typed pool" lang="shell" terminal>
            {REJECTED}
          </Code>
        </div>
        <p className="ink2" style={{ marginTop: 18 }}>
          The typed kernel changes Balancer in exactly the two places it rounded an outgoing amount down. Everything else
          is identical, every StableMath call included, and the typed kernel reaches StableMath only through{" "}
          <a href={`${BLOB}/ingots/balancer_v2/src/pool/typed/math.fe`}>signatures that demand admitted amounts</a>.
        </p>
      </Section>

      <Section eyebrow="Exhaustive search" title={`${n(exploration.states)} pool states, every operation, three kernels.`}>
        <p className="ink2" style={{ marginBottom: 20 }}>
          Natively, in exact integers: {(headline.operationsPerKernel / 1e6).toFixed(2)} million operations per kernel.
          Each cell counts operations that lowered the value behind each pool share, and operations that stored an
          invariant its balances do not support.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Operation</th>
                <th className="n">Balancer (faithful)</th>
                <th className="n">Typed</th>
                <th className="n">Typed + guard</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 4).map((r) => (
                <tr key={r.op}>
                  <td className="num">{r.op}</td>
                  {(["faithful", "typed", "guarded"] as const).map((k) => (
                    <td className="n" key={k}>
                      {n(r[k].value_per_bpt_losses)} / {n(r[k].stored_invariant_violations)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="ink2" style={{ marginTop: 18 }}>
          The types remove the losses at Balancer&apos;s two rounding sites. What remains comes from StableMath&apos;s own
          precision, identical with and without the types, and the guard rejects exactly those operations.
        </p>
        <div className="table-wrap" style={{ marginTop: 20 }}>
          <table>
            <thead>
              <tr>
                <th>Greedy attacker, repeated exact-out exits</th>
                <th className="n">Balancer</th>
                <th className="n">Typed</th>
                <th className="n">Guarded</th>
              </tr>
            </thead>
            <tbody>
              {exploration.greedy_attacks.map((a) => (
                <tr key={`${a.b0}-${a.rate}`}>
                  <td>
                    {a.b0} / {a.b1} wei, rate {(a.rate / 1e18).toFixed(3)}, amp {a.amp / 1000}
                  </td>
                  {(["faithful", "typed", "guarded"] as const).map((k) => (
                    <td className="n" key={k}>
                      {a[k].attacker_gain_wad > 0 ? "+" : ""}
                      {(a[k].attacker_gain_wad / 1e18).toFixed(3)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ fontSize: 14 }}>
          The attacker&apos;s gain, in invariant units. Positive only on Balancer&apos;s arithmetic.
        </p>
      </Section>

      <Section eyebrow="On an EVM" title="The three kernels as deployed contracts.">
        <Claims claims={evm.claims} />
        <div className="table-wrap" style={{ marginTop: 22 }}>
          <table>
            <thead>
              <tr>
                <th>Gas, the pool&apos;s real parameters</th>
                <th className="n">Balancer (faithful)</th>
                <th className="n">Typed</th>
                <th className="n">Guarded</th>
              </tr>
            </thead>
            <tbody>
              {gasRows.map((g) => (
                <tr key={g.op}>
                  <td className="num">{g.op}</td>
                  <td className="n">{n(g.faithful)}</td>
                  <td className="n">
                    {n(g.typed)} <span className="muted">({rel(g.typed, g.faithful)})</span>
                  </td>
                  <td className="n">
                    {n(g.guarded)} <span className="muted">({rel(g.guarded, g.faithful)})</span>
                  </td>
                </tr>
              ))}
              {Object.entries(levels).map(([level, sizes]) => (
                <tr key={level}>
                  <td className="num">bytecode, -{level}</td>
                  <td className="n">{n(sizes.faithful)} B</td>
                  <td className="n">{n(sizes.typed)} B</td>
                  <td className="n">{n(sizes.guarded)} B</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="ink2" style={{ marginTop: 16 }}>
          The type machinery itself compiles away. The typed contract&apos;s near-constant extra cost is real work: reading
          its rate through the banded boundary and checking its factors on every operation. The guard costs one invariant
          solve on swaps. Value per share under the EVM attack: {evm.attack.faithful.value_per_bpt_change} on
          Balancer&apos;s arithmetic, {evm.attack.typed.value_per_bpt_change} typed, starting from{" "}
          {wad(evm.attack.faithful.value_per_bpt_start_wad, 2)}.
        </p>
        <p style={{ marginTop: 22 }}>
          <Link href="/docs/balancer">The full account, with every limit →</Link>
        </p>
      </Section>
    </>
  );
}
