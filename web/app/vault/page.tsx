import type { Metadata } from "next";
import Link from "next/link";
import { Claims } from "@/components/Claims";
import { Code } from "@/components/Code";
import { PageHead, Section } from "@/components/PageHead";
import { Stat } from "@/components/Stat";
import { n } from "@/lib/format";
import { headline } from "@/lib/numbers";
import { vault } from "@/lib/results";

export const metadata: Metadata = { title: "ERC-4626 vault" };

const DEPOSIT = `/// Shares for depositing \`assets\`: assets come in, shares go out.
pub fn preview_deposit<A>(_ v: Vault<A>, _ assets: Quantity<A, In, Given>) -> Quantity<
    Shares<A>,
    Out,
    Settled,
> {
    exchange(
        assets,
        numerator: v.total_shares.raw() + 1,
        denominator: v.total_assets.raw() + 1,
    )
}`;

const EXCHANGE = `/// Exchanges a given amount of \`A\` for an amount of \`B\` at the ratio
/// \`numerator / denominator\`, such as a vault's shares per asset. What the
/// protocol gives in return moves the other way, \`G::Opposite\`, and is rounded
/// by that direction's obligation: a payout rounds down, a charge rounds up.
/// So the rounding follows from which way the given amount moves.
pub fn exchange<A, B, G: Flow>(
    _ given: Quantity<A, G, Given>,
    numerator: u256,
    denominator: u256,
) -> Quantity<B, G::Opposite, Settled> {
    Quantity { v: <G::Opposite as Flow>::Obligation::mul_div(given.v, numerator, denominator) }
}`;

const OPS = [
  ["deposit", "assets, In", "shares, Out", "down"],
  ["mint", "shares, Out", "assets, In", "up"],
  ["withdraw", "assets, Out", "shares, In", "up"],
  ["redeem", "shares, In", "assets, Out", "down"],
];

export default function Vault() {
  const fns = vault.functions as Record<string, { vectors: number; rounding_decides: number }>;
  return (
    <>
      <PageHead
        eyebrow="Beyond the incidents · ERC-4626"
        title={
          <>
            Four roundings. <em>None written down.</em>
          </>
        }
        lede={
          <>
            EIP-4626 fixes four rounding directions, and every vault must get all four right by hand. Written with
            Dimension, each operation states which way its given amount moves, and the rest follows. The roundings it
            derives are exactly the ones OpenZeppelin&apos;s audited ERC4626 names.
          </>
        }
      />
      <Section eyebrow="How" title="The direction of what the vault gives back is the opposite of what it receives.">
        <div className="grid-2">
          <Code title="ingots/vault/src/vault.fe" lang="fe">
            {DEPOSIT}
          </Code>
          <Code title="ingots/dimension/src/value.fe" lang="fe">
            {EXCHANGE}
          </Code>
        </div>
        <div className="table-wrap" style={{ marginTop: 22 }}>
          <table>
            <thead>
              <tr>
                <th>Operation</th>
                <th>Given</th>
                <th>Given back</th>
                <th>Rounding that follows</th>
                <th className="n">Vectors equal to OpenZeppelin</th>
                <th className="n">Where the rounding decides</th>
              </tr>
            </thead>
            <tbody>
              {OPS.map(([op, given, back, rounding]) => {
                const f = fns[`preview${op[0].toUpperCase()}${op.slice(1)}`];
                return (
                  <tr key={op}>
                    <td className="num">{op}</td>
                    <td>{given}</td>
                    <td>{back}</td>
                    <td>{rounding}</td>
                    <td className="n">{n(f.vectors)}</td>
                    <td className="n">{n(f.rounding_decides)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>
      <Section eyebrow="Checked" title="Against OpenZeppelin, and against the exact rational result.">
        <div className="grid-3" style={{ marginBottom: 24 }}>
          <Stat value={n(headline.vaultVectors)} label="vectors equal to OpenZeppelin Contracts v5.1.0's ERC4626, in the same states" run="make vault" />
          <Stat value={n(headline.vaultDecides)} label="of them with a fractional exact result: the direction decided the answer" run="make vault" />
          <Stat value="32,768" label="vault states, every preview exact against the rational result, on both backends" run="make unit" />
        </div>
        <Claims claims={vault.claims} />
        <p style={{ marginTop: 22 }}>
          <Link href="/docs/vault">The vault, with its limits →</Link>
        </p>
      </Section>
    </>
  );
}
