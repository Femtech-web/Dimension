# Guarantees

What Dimension guarantees, at which layer, how strongly each guarantee is
established, and what it does not guarantee. Status words:

- **verified**: checked against an independent reference, such as Balancer's
  Solidity, a deployed contract, the other backend, or the real chain;
- **tested**: covered by automated tests that run in `make ci`;
- **implemented**: in the code, without a dedicated test;
- **planned**: not built.

## Layers

| Layer | What it stops | Mechanism | Evidence | Status |
|---|---|---|---|---|
| Compile time | A price used for the wrong pair; prices composed without a shared asset; collateral added to debt | `Price<B, Q>` and `Value<Q, V>` phantom parameters; `Mul` only through a shared asset | compile-fail cases with twins; Moonwell's MIP-X43 configuration written against the real Base registry | tested |
| Compile time | An amount rounded the wrong way when admitted or settled; a scaled amount handed to the math without admission | `Flow` and `Stage` types; `admit` and `settle` are the only producers; the typed kernel reaches StableMath only through `Admitted` signatures | Balancer's `_upscale` line put back into the typed pool is rejected; the explorer measures the effect | verified |
| Compile time | A third rounding direction, a custom flow, an incoherent risk policy, an asset with more than 18 decimals | sealed traits; `where` predicates on associated constants | compile-fail cases | tested |
| Compile time | Trusted values built from raw numbers; test constructors reached from production code | private fields; `unsafe fn` constructors gated by `allow_unsafe`; `make unsafe-policy` | compile-fail cases `forge_price`, `forge_admitted_quantity`, `test_constructor_from_production_root`; CI policy check | tested |
| Compile time | An oracle read in code that has not declared it calls out and reads the clock | effects: `read` requires `uses (call: mut Call, ctx: Ctx)` | compile-fail case `oracle_read_without_effects` | tested |
| Bind time | A feed that reports different decimals than declared | `verify` in the constructor, `WrongDecimals` | oracle unit tests; on a Base fork, cbETH/ETH declared as an 8-decimal USD feed fails to deploy | verified |
| Read time | Non-positive, future, stale or out-of-band answers; out-of-band rates | `read`, `read_rate` | oracle unit tests; on a Base fork, cbETH/ETH declared as cbETH/USD fails its first read, and a stale ETH/USD leg is refused | verified |
| Runtime | An operation that lowers the value behind a pool share, whatever its cause | `preserves_share_value`, exact 512-bit comparison; `GuardedPool` | 0 losses over 3.14 million operations per kernel; rejects exactly the 17 that would lose; EVM attack | verified |
| External | That an address is the feed it is declared to be | none: a reviewed declaration | stated here | assumption |

## What the types establish, precisely

- **Every admitted and settled amount is rounded against the trader.** The only
  producers of `Admitted` and `Settled` quantities take their rounding from
  the flow direction. A call site cannot name a direction.
- **The typed Balancer kernel names no rounding for any amount that moves.**
  Two directions in it are still explicit, both Balancer's and both in the
  pool's favour:
  - held balances are upscaled down, because they are holdings, not flows;
  - the swap fee on an exact-in swap is rounded up, as in
    `_subtractSwapFeeAmount`.
- **A `Price<B, Q>` came from a checked read, or from composing two of them.**
  `assume_price` exists for tests, and only a root ingot with `allow_unsafe`
  can call it.

What they do not establish:

- **That a label is true.** `given` and `owed` attach a direction to a raw
  number, and `given<T, In>(x)` compiles even if `x` is in fact leaving. Such a
  mislabel is visible in review. What does not compile is changing a
  direction after rounding: a payout settled with payout rounding cannot be
  used where a charge is required (`payout_settled_as_charge`).
- **That StableMath is precise.** Its own rounding inside the invariant
  solvers is outside the scaling boundary. See the residuals below.
- **Anything about arbitrary financial semantics.** Dimension encodes asset
  identity, pairs, decimals, direction and the policies stated as predicates.
  It does not prove a protocol solvent.

## Measured residuals

From `make explore` over 4,608 pool states (exact integers, zero fees):

| Operation | Faithful | Typed | Guarded |
|---|---|---|---|
| exitGivenOut: value-per-share losses | 57,990 (worst 14.86%) | 8 (worst 0.0203%) | 0 (8 rejected) |
| exitGivenOut: stored-invariant violations | 108,976 | 16 | 0 |
| swapGivenOut: value-per-share losses | 48 (worst 6.17%) | 0 | 0 |
| joinGivenIn: value-per-share losses | 9 (worst 0.0599%) | 9 | 0 (9 rejected) |
| joinGivenIn: stored-invariant violations | 14 | 14 | 0 |
| joinGivenOut: stored-invariant violations | 57 | 57 | 0 |

Typed rounding removes the losses at Balancer's two `_upscale` sites. The
losses that remain come from StableMath's own precision, and the joins lose
identically with or without types. The guard rejects exactly the operations
that would lose, and no others. It removes the stored-invariant violations
without rejecting anything, by storing the invariant of the actual balances.

**Dust reverts.** The typed kernels revert 288 exact-out swaps that Balancer
accepts, all of them 1 wei out of a 2-wei rated balance. Rounded up, that wei
is the whole scaled balance, so StableMath cannot pay it. Balancer rounded it
down and paid it for free.

## Cost

| Measure | Faithful | Typed | Guarded |
|---|---|---|---|
| swapGivenOut gas | 15,669 | 16,695 (+6.5%) | 23,130 (+47.6%) |
| exitGivenOut gas | 21,116 | 21,478 (+1.7%) | 22,313 (+5.7%) |
| runtime bytecode | 7,414 B | 9,233 B | 9,675 B |

Gas is measured on a pool the size of the osETH/wETH pool before the exploit,
with 10 tokens out (`make evm`). The typed contract also reads its rate through
the banded boundary on every operation, which the faithful one does not.

The type machinery itself is free: typed and raw code compile to byte-identical
runtime bytecode at `-O1`, `-O2` and `-Os` in the probes (`make probes`). At
`-O0` they differ.

## Fidelity of the Balancer demonstration

| Claim | Level | Status |
|---|---|---|
| FixedPoint, Math, StableMath equal Balancer's Solidity, reverts included | 22 functions, 220,000 vectors | verified |
| The pool kernel returns what the deployed osETH/wETH pool returned | 330 swap quotes and 165 exact-out BPT exits at block 23,717,399 | verified |
| The kernel models the whole protocol | one two-token pool, no protocol fees, no Vault batching, rate cache or amplification ramp | not claimed |
| The attacker's transaction replays against the Fe kernel | | not done |

## The unsafe boundary

Dimension's trust rests on protocol code living in ingots that cannot reach
`unsafe`:

- `dimension`, `balancer_v2` and `moonwell` set no `allow_unsafe`.
- The only `unsafe` in them is Dimension's test constructors in
  `value::testing`.
- `make unsafe-policy` enforces both rules in CI.

A root ingot with `allow_unsafe` can still forge any value with a pointer cast.
The probe `bypass_unsafe_in_root` documents this. `balancer_explorer` is such a
root, because it feeds rates to the typed kernel in simulation. It builds no
contract.
