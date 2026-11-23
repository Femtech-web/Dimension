// The saved reports, synced from docs/results by scripts/sync.mjs.
import compat from "@/data/results/compat.json";
import compileFail from "@/data/results/compile-fail.json";
import consumer from "@/data/results/consumer.json";
import differential from "@/data/results/differential.json";
import evm from "@/data/results/evm.json";
import exploration from "@/data/results/exploration.json";
import feeds from "@/data/results/feeds.json";
import fidelity from "@/data/results/fidelity.json";
import live from "@/data/results/live.json";
import moonwell from "@/data/results/moonwell.json";
import mutants from "@/data/results/mutants.json";
import native from "@/data/results/native.json";
import probes from "@/data/results/probes.json";
import replay from "@/data/results/replay.json";
import unit from "@/data/results/unit.json";
import vault from "@/data/results/vault.json";
import wasm from "@/data/results/wasm.json";
import meta from "@/data/meta.json";

export { compat, compileFail, consumer, differential, evm, exploration, feeds, fidelity, live, meta, moonwell, mutants, native, probes, replay, unit, vault, wasm };

export type Claim = { question: string; holds: boolean; evidence: string };

/** Every suite's claims, in the order a reader meets them, with the command that reproduces each. */
export function allClaims(): { suite: string; title: string; command: string; claims: Claim[] }[] {
  const s = differential.summary;
  return [
    {
      suite: "differential",
      title: "Balancer's Solidity against the Fe port",
      command: "make differential",
      claims: [{
        question: differential.question,
        holds: s.mismatches === 0,
        evidence: `${s.vectors.toLocaleString("en-US")} vectors over ${s.functions} functions: ${s.both_succeeded.toLocaleString("en-US")} identical results, ${s.both_reverted.toLocaleString("en-US")} identical reverts, ${s.mismatches} mismatches`,
      }],
    },
    { suite: "fidelity", title: "The Fe port against the deployed pool", command: "make fidelity", claims: fidelity.claims },
    { suite: "replay", title: "The attacker's own transactions, step by step", command: "make replay", claims: replay.claims },
    { suite: "exploration", title: "Native search over the three kernels", command: "make explore", claims: exploration.claims },
    { suite: "evm", title: "The three pool contracts on an EVM", command: "make evm", claims: evm.claims },
    { suite: "moonwell", title: "Moonwell's cbETH market on Base forks", command: "make moonwell", claims: moonwell.claims },
    { suite: "feeds", title: "Each declared feed against Chainlink's directory", command: "make feeds", claims: feeds.claims },
    { suite: "vault", title: "The ERC-4626 vault against OpenZeppelin", command: "make vault", claims: vault.claims },
    { suite: "live", title: "The deployment on Base Sepolia, read back from the chain", command: "make live", claims: live.claims },
    { suite: "wasm", title: "The Balancer kernels in WebAssembly, against the EVM", command: "make wasm", claims: wasm.claims },
    { suite: "native", title: "The same kernels as a native library, called from C", command: "make native", claims: native.claims },
    { suite: "consumer", title: "Dimension as someone else's dependency", command: "make consumer", claims: consumer.claims },
    { suite: "compat", title: "The same library and tests on Fe 26.7.0", command: "make compat", claims: compat.claims },
    { suite: "mutants", title: "Planted bugs, each caught by the check meant for it", command: "make mutants", claims: mutants.claims },
  ];
}
