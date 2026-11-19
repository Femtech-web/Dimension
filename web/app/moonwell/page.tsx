import type { Metadata } from "next";
import Link from "next/link";
import { Claims } from "@/components/Claims";
import { Code } from "@/components/Code";
import { PageHead, Section } from "@/components/PageHead";
import { PriceChart } from "@/components/PriceChart";
import { n, shortHash } from "@/lib/format";
import { pricePoints } from "@/lib/numbers";
import { feeds, moonwell } from "@/lib/results";
import { BLOB } from "@/lib/site";

export const metadata: Metadata = { title: "Moonwell MIP-X43" };

const REGISTRY = `pub const CBETH_ETH: Feed<CBETH, ETH> = feed(
    Address::new(0x806b4Ac04501c29769051e42783cF04dCE41440b),
    decimals: 18,
    max_age: 90_000,
    min_wad: WAD,
    max_wad: 3 * WAD / 2,
)

pub const ETH_USD: Feed<ETH, USD> = feed(
    Address::new(0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70),
    decimals: 8,
    max_age: 1_800,
    min_wad: 100 * WAD,
    max_wad: 100_000 * WAD,
)`;

const MISTAKE = `// MIP-X43 listed cbETH with the markets priced by one USD feed,
// and gave it the cbETH/ETH exchange rate as that feed.
pub const CBETH_USD: Feed<CBETH, USD> = CBETH_ETH

error[8-0000]: type mismatch
expected \`Feed<CBETH, USD>\`, but \`Feed<CBETH, ETH>\` is given

// The fix: price cbETH in USD through both legs.
pub const CBETH_USD: ViaEth<CBETH> = ViaEth { leg: CBETH_ETH, eth_usd: ETH_USD }`;

const basescan = (tx: string) => `https://basescan.org/tx/${tx}`;

export default function Moonwell() {
  const ref = moonwell.reference;
  const swapped = feeds.misdeclared.find((f) => f.name === "SWAPPED_ETH_USD")!;
  const layers = moonwell.layers as { layer: string; case: string; error?: string; note?: string; rejected: boolean }[];
  return (
    <>
      <PageHead
        eyebrow="Moonwell MIP-X43 · Base · 2026-02-15"
        title={
          <>
            1.12 USD, from the same feeds. <em>Or 2,206.68.</em>
          </>
        }
        lede={
          <>
            A governance proposal gave Moonwell&apos;s cbETH market the cbETH/ETH exchange rate as its USD price. For eight
            days the market valued cbETH at about 1.12 USD, and liquidators seized collateral against almost nothing.
            Dimension&apos;s oracle, deployed on forks of Base across those eight days, read the same two Chainlink feeds.
          </>
        }
      />

      <Section eyebrow="The fork runs" title="Correct at every block. Identical to Moonwell, to the wei, wherever Moonwell was right.">
        <PriceChart points={pricePoints()} />
        <div style={{ marginTop: 24 }}>
          <Claims claims={moonwell.claims} />
        </div>
      </Section>

      <Section eyebrow="Where the mistake is stopped" title="Wherever it is made.">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Layer</th>
                <th>The mistake, made as</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {layers.map((l) => (
                <tr key={l.case}>
                  <td className="num">{l.layer}</td>
                  <td>{l.case}</td>
                  <td>
                    {l.rejected ? (
                      <span className="status good">
                        <i aria-hidden="true">✓</i>
                        {l.error}
                      </span>
                    ) : (
                      <span className="status bad">
                        <i aria-hidden="true">!</i>every on-chain check accepts it
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              <tr>
                <td className="num">review</td>
                <td>the same kind of feed, before deployment: Chainlink&apos;s cbETH/USD feed declared as ETH/USD</td>
                <td>
                  <span className="status good">
                    <i aria-hidden="true">✓</i>make feeds: listed as {swapped.listed_as}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="grid-2" style={{ marginTop: 24 }}>
          <Code title="ingots/moonwell/src/registry.fe: each feed declared once, with its pair" lang="fe">
            {REGISTRY}
          </Code>
          <Code title="MIP-X43, written against that registry" lang="fe">
            {MISTAKE}
          </Code>
        </div>
      </Section>

      <Section eyebrow="Before deployment" title="The one fact no chain check can see, checked against Chainlink.">
        <p className="ink2">
          No check on chain can prove an address is the feed it is declared to be. Chainlink&apos;s published directory
          lists every feed&apos;s address with its pair, decimals and heartbeat.{" "}
          <a href={`${BLOB}/scripts/feeds/feed_check.py`}>
            <code>feed_check.py</code>
          </a>{" "}
          requires each declaration to match it, and the chain to agree. It runs here on the registry, and on two wrong
          declarations that both compile. The second passes every check Dimension makes on chain.
        </p>
        <div style={{ marginTop: 20 }}>
          <Claims claims={feeds.claims} />
        </div>
        <div style={{ marginTop: 20 }}>
          <Code title="before deploying your own registry" lang="sh" terminal>
            {"python3 scripts/feeds/feed_check.py src/registry.fe --network base"}
          </Code>
        </div>
        <p className="muted" style={{ fontSize: 14 }}>
          Checked at Base block {n(feeds.chain.block)}. The trust that remains is in Chainlink&apos;s own directory, at
          review time.
        </p>
      </Section>

      <Section eyebrow="The on-chain record" title="Every fact read from Base, and checked again by the fork test.">
        <div className="table-wrap">
          <table>
            <tbody>
              <tr>
                <td>Moonwell&apos;s oracle</td>
                <td className="num">{ref.moonwell_oracle}</td>
              </tr>
              <tr>
                <td>The cbETH market</td>
                <td className="num">{ref.cbeth_market}</td>
              </tr>
              <tr>
                <td>Last block priced correctly</td>
                <td className="num">{n(ref.last_correct_block)}</td>
              </tr>
              <tr>
                <td>MIP-X43 executes</td>
                <td className="num">
                  block {n(ref.mip_x43_block)}, <a href={basescan(ref.mip_x43_tx)}>{shortHash(ref.mip_x43_tx)}</a>
                </td>
              </tr>
              <tr>
                <td>The fix executes</td>
                <td className="num">
                  block {n(ref.fixed_block)}, <a href={basescan(ref.fix_tx)}>{shortHash(ref.fix_tx)}</a>
                </td>
              </tr>
              {Object.entries(ref.feeds).map(([pair, address]) => (
                <tr key={pair}>
                  <td>Chainlink {pair}</td>
                  <td className="num">{address}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p style={{ marginTop: 22 }}>
          <Link href="/docs/moonwell">The full record, block by block →</Link>
        </p>
      </Section>
    </>
  );
}
