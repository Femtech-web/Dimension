// Headline figures, each computed from a saved report, never written by hand.
import { compileFail, differential, evm, exploration, fidelity, moonwell, mutants, replay, vault } from "./results";
import type { PricePoint } from "@/components/PriceChart";
import type { ReplayTx } from "@/components/ReplayChart";

const WAD = 1e18;
const kernels = ["faithful", "typed", "guarded"] as const;
type Op = { tried: number; value_per_bpt_losses: number; stored_invariant_violations: number; reverted: number };

export const headline = {
  vectors: differential.summary.vectors,
  quotes: fidelity.summary.compared,
  steps: replay.attacks.reduce((s, a) => s + a.faithful.steps, 0),
  stepsEqual: replay.attacks.reduce((s, a) => s + a.faithful.steps_equal_to_balancer, 0),
  states: exploration.states,
  operationsPerKernel: Object.values(exploration.kernels.faithful.by_operation as Record<string, Op>).reduce((s, o) => s + o.tried, 0),
  mutantsCaught: mutants.mutants.filter((m) => m.caught).length,
  mutants: mutants.mutants.length,
  mutantLayers: new Set(mutants.mutants.map((m) => m.layer)).size,
  compileFail: compileFail.summary.cases,
  vaultVectors: Object.values(vault.functions as Record<string, { vectors: number }>).reduce((s, f) => s + f.vectors, 0),
  vaultDecides: Object.values(vault.functions as Record<string, { rounding_decides: number }>).reduce((s, f) => s + f.rounding_decides, 0),
  moonwellBlocks: moonwell.prices.length,
};

/** Losing operations per kind and kernel in the search. */
export function search() {
  const ops = ["swapGivenOut", "exitGivenOut", "joinGivenIn", "joinGivenOut", "swapGivenIn", "exitGivenIn"];
  return ops.map((op) => ({
    op,
    ...Object.fromEntries(kernels.map((k) => [k, (exploration.kernels[k].by_operation as Record<string, Op>)[op]])),
  })) as { op: string; faithful: Op; typed: Op; guarded: Op }[];
}

export function gas() {
  const per = evm.gas.per_operation as Record<string, Record<string, number>>;
  return Object.keys(per.faithful).map((op) => ({
    op,
    faithful: per.faithful[op],
    typed: per.typed[op],
    guarded: per.guarded[op],
  }));
}

export function replayTxs(): ReplayTx[] {
  return replay.attacks.map((a) => {
    const typed = a.typed as unknown as { value_per_bpt_by_step_wad: number[]; steps_completed: number };
    return {
      attack: a.attack,
      block: a.block,
      start: a.faithful.value_per_bpt_start_wad / WAD,
      faithful: a.faithful.value_per_bpt_by_step_wad.map((v: number) => v / WAD),
      typed: typed.value_per_bpt_by_step_wad.map((v: number) => v / WAD),
      stop: typed.steps_completed,
      reason: "BAL#001",
      kinds: a.faithful.kinds_by_step,
    } as ReplayTx;
  });
}

export function pricePoints(): PricePoint[] {
  return moonwell.prices.map((p) => ({
    block: p.block,
    ts: p.timestamp,
    moonwell: p.moonwell_wad / WAD,
    fe: p.fe_wad / WAD,
    window: p.moonwell_oracle === "mip-x43",
  }));
}
