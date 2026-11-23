import type { Metadata } from "next";
import Link from "next/link";
import { BrowserKernels } from "@/components/BrowserKernels";
import { Claims, Status } from "@/components/Claims";
import { Code } from "@/components/Code";
import { LiveReads, type LiveAddresses } from "@/components/LiveReads";
import { PageHead, Section } from "@/components/PageHead";
import { n, shortHash, wad } from "@/lib/format";
import { live } from "@/lib/results";
import { BLOB } from "@/lib/site";

export const metadata: Metadata = { title: "Live on Base Sepolia" };

const ROLES: Record<string, [string, string]> = {
  FaithfulPool: ["Balancer V2's arithmetic, ported exactly", "ingots/balancer_v2/src/contracts.fe"],
  TypedPool: ["The same pool, its amounts typed by direction", "ingots/balancer_v2/src/contracts.fe"],
  GuardedPool: ["The typed pool with the runtime share-value guard", "ingots/balancer_v2/src/contracts.fe"],
  MockRateProvider: ["osETH's rate as the drained pool read it: 1.21", "contracts/reference/src/MockRateProvider.sol"],
  CbethUsdOracle: ["cbETH in USD through ETH, from Chainlink's Base Sepolia feeds", "ingots/live/src/contracts.fe"],
  DeclaredCbethEthAsUsd: ["MIP-X43's mistake: cbETH/ETH declared as cbETH/USD, with its real decimals", "ingots/moonwell/src/contracts.fe"],
  DeclaredCbethUsd: ["Chainlink's cbETH/USD, declared correctly", "ingots/moonwell/src/contracts.fe"],
  TypedVault: ["The ERC-4626 vault's four previews", "ingots/vault/src/contracts.fe"],
  LiveRecorder: ["Solidity: calls the Fe contracts through ordinary interfaces and logs each outcome with the exact revert data", "contracts/reference/src/LiveRecorder.sol"],
};

type Attack = {
  pool: string;
  tx: string;
  exits: number;
  succeeded: boolean;
  rate_before: string;
  rate_after: string;
  reason: string | null;
};

export default function Live() {
  const contracts = live.contracts as Record<string, { address: string; tx: string; block: number }>;
  const address = (name: string) => `${live.explorer}/address/${contracts[name].address}`;
  const tx = (hash: string) => `${live.explorer}/tx/${hash}`;
  const attacks = live.attacks as Attack[];
  // The value per BPT the chain recorded after each kernel's longest batch that ran.
  const ended = (pool: string) =>
    attacks.filter((a) => a.pool === pool && a.succeeded).sort((a, b) => b.exits - a.exits)[0].rate_after;
  const chainEnds = { faithful: ended("FaithfulPool"), typed: ended("TypedPool"), guarded: ended("GuardedPool") };
  const addresses: LiveAddresses = {
    oracle: contracts.CbethUsdOracle.address,
    misdeclared: contracts.DeclaredCbethEthAsUsd.address,
    declared: contracts.DeclaredCbethUsd.address,
    vault: contracts.TypedVault.address,
    pools: ["FaithfulPool", "TypedPool", "GuardedPool"].map((p) => [p, contracts[p].address]),
    cbethEth: live.oracle.feeds.CBETH_ETH,
    ethUsd: live.oracle.feeds.ETH_USD,
  };
  return (
    <>
      <PageHead
        eyebrow={`Live · Base Sepolia · chain ${live.chain_id}`}
        title={
          <>
            Not a fork. <em>A public chain.</em>
          </>
        }
        lede={
          <>
            The three pools, the cbETH oracle and the vault, compiled by Fe {live.fe.version} from this repository and
            deployed on Base Sepolia. The attacker&apos;s batch ran against each pool, and MIP-X43&apos;s mistake was
            declared against Chainlink&apos;s real feeds. Each outcome is in an event on chain, with its exact revert
            data, and <code>make live</code> reads all of it back.
          </>
        }
      />

      <Section eyebrow="Read it now" title="From your browser, at one block, through Base Sepolia's public RPC.">
        <LiveReads addresses={addresses} />
      </Section>

      <Section eyebrow="The attack, on chain" title="One batch. Three pools. One transaction each.">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pool</th>
                <th className="n">Exits</th>
                <th>Outcome</th>
                <th className="n">Value per BPT</th>
                <th>Transaction</th>
              </tr>
            </thead>
            <tbody>
              {attacks.map((a) => (
                <tr key={a.tx}>
                  <td>{a.pool}</td>
                  <td className="n">{a.exits}</td>
                  <td>
                    {a.succeeded ? (
                      <Status holds={BigInt(a.rate_after) >= BigInt(a.rate_before)} yes="ran, value rose" no="ran, value fell" />
                    ) : (
                      <span className="status good">
                        <i aria-hidden="true">✓</i>
                        reverted {a.reason}
                      </span>
                    )}
                  </td>
                  <td className="n">
                    {wad(BigInt(a.rate_before), 4)} → {wad(BigInt(a.rate_after), 4)}
                  </td>
                  <td className="num">
                    <a href={tx(a.tx)}>{shortHash(a.tx)}</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="ink2" style={{ marginTop: 16 }}>
          The batch is the one that drains the pool rounding as Balancer V2 did, planned exit by exit against its
          arithmetic. On the typed pools its last exit asks for 1 of the 2 wei of osETH left. Rounded up, as an amount
          leaving the pool must be, that is everything the pool holds, and StableMath reverts. Without that exit, the
          batch raises the value behind each share.{" "}
          <Link href="/balancer">Why the rounding decides it →</Link>
        </p>
        <p className="ink2" style={{ marginTop: 12 }}>
          Each batch ran through LiveRecorder, a Solidity contract that calls the Fe pools through an ordinary
          interface; the typed pools&apos; <code>BAL#004</code> reached it as an ordinary revert.{" "}
          <Link href="/docs/interop">Using Dimension from Solidity, JavaScript and C →</Link>
        </p>
      </Section>

      <Section eyebrow="Run it in your browser" title="The same batch, through the same Fe kernels, in WebAssembly.">
        <p className="ink2" style={{ marginTop: -8, marginBottom: 22, maxWidth: 760 }}>
          The kernels the pool contracts run, compiled by Fe to WebAssembly from the same source and run here, in this
          page. Play the batch, or move along it, to see each kernel&apos;s value per BPT after every exit.
        </p>
        <BrowserKernels chain={chainEnds} />
      </Section>

      <Section eyebrow="What the chain recorded" title="Every claim, read back from the chain.">
        <Claims claims={live.claims} />
        <p className="muted" style={{ fontSize: 14, marginTop: 14 }}>
          Checked at block {n(live.checked_at.block)}. Fe contracts are compared byte for byte with what{" "}
          <code>fe build</code> produces here, and the batch and its results with LivePlan&apos;s run of it in forge.
        </p>
      </Section>

      <Section eyebrow="Every contract" title="Deployed from one account, nothing else in between.">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Contract</th>
                <th>What it is</th>
                <th>Address</th>
              </tr>
            </thead>
            <tbody>
              {Object.keys(ROLES).filter((name) => contracts[name]).map((name) => (
                <tr key={name}>
                  <td>
                    <a href={`${BLOB}/${ROLES[name][1]}`}>{name}</a>
                  </td>
                  <td className="ink2">{ROLES[name][0]}</td>
                  <td className="num">
                    <a href={address(name)}>{shortHash(contracts[name].address)}</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ fontSize: 14, marginTop: 14 }}>
          Deployer <a href={`${live.explorer}/address/${live.deployer}`} className="num">{shortHash(live.deployer)}</a>.
          The pools are test contracts with open entry points, as in the fork tests; the record is in the transactions
          below, which no later call can change.
        </p>
      </Section>

      <Section eyebrow="Every transaction" title={`${live.transactions.length} transactions, in order.`}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>What</th>
                <th className="n">Block</th>
                <th className="n">Gas</th>
                <th>Transaction</th>
              </tr>
            </thead>
            <tbody>
              {live.transactions.map((t) => (
                <tr key={t.hash}>
                  <td>{t.action}</td>
                  <td className="n">{n(t.block)}</td>
                  <td className="n">{n(t.gas_used)}</td>
                  <td className="num">
                    <a href={tx(t.hash)}>{shortHash(t.hash)}</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section eyebrow="Check it yourself">
        <Code title="from a clone, with forge installed" lang="sh" terminal>
          {"make live            # read the deployment back from Base Sepolia\nmake live-rehearse  # deploy it all again on a local fork; no key needed"}
        </Code>
      </Section>
    </>
  );
}
