# Balancer V2: the flagship

On 2025-11-03, Balancer V2's composable stable pools were drained across
several chains; estimates of the loss range from 95M to 128M USD. This document
covers four things:

1. how Dimension reproduces the mechanism faithfully;
2. how that reproduction is verified against Balancer's own code and the
   deployed pool;
3. what the types change;
4. what the measurements show.

## The bug

A composable stable pool keeps balances in each token's own units and does its
math in 18-decimal internal units, scaled by each token's rate. `_upscale`
converts an amount into internal units, and it always rounds down. Its own
comment records the decision
([`ScalingHelpers.sol`](../third_party/balancer-v2/pkg/solidity-utils/contracts/helpers/ScalingHelpers.sol)):

```solidity
function _upscale(uint256 amount, uint256 scalingFactor) pure returns (uint256) {
    // Upscale rounding wouldn't necessarily always go in the same direction: in a swap for example the balance of
    // token in should be rounded up, and that of token out rounded down. This is the only place where we round in
    // the same direction for all amounts, as the impact of this rounding is expected to be minimal.
    return FixedPoint.mulDown(amount, scalingFactor);
}
```

For an amount coming in, rounding down is safe: the pool counts slightly less
than it received. For an amount going out, in an exact-out swap or an exact-out
BPT exit, it is the wrong direction. The pool counts slightly less than leaves
it, so its invariant drifts down with each such operation, and with it the
price of its shares. The attacker batched exact-out swaps at amounts where the
gap was largest, deflated the invariant, and bought shares cheaply.

In Dimension, the direction of a rounding is not a choice made at the call
site. An amount leaving the pool is a `Quantity<T, Out, Given>`, and the only
way into internal units is `admit`, which rounds `Out` up.

## What was ported

From Balancer's monorepo at commit `e91a2b6` (pinned in
[`third_party/balancer-v2`](../third_party/balancer-v2), with its
[provenance](../third_party/balancer-v2/PROVENANCE.md)):

| Balancer | Fe | How |
|---|---|---|
| `FixedPoint`, `Math` | [`stable/fixed_point.fe`](../ingots/balancer_v2/src/stable/fixed_point.fe), [`stable/math.fe`](../ingots/balancer_v2/src/stable/math.fe) | line by line, with Solidity 0.7's wrapping arithmetic and Balancer's own checks |
| `StableMath` | [`stable/stable_math.fe`](../ingots/balancer_v2/src/stable/stable_math.fe) | line by line, generic over 2 to 5 tokens (`const N: usize where N >= 2, N <= 5`) |
| `ComposableStablePool` swap, join and exit paths, `BaseGeneralPool`, scaling helpers | [`pool/faithful.fe`](../ingots/balancer_v2/src/pool/faithful.fe) | the operations a two-token pool performs, including `_upscale`'s rounding |

Balancer's checks are kept as checks, with Balancer's error codes, so even a
revert can be compared byte for byte. Every arithmetic function declares
failure as an effect (`uses (check: mut Check)`). On the EVM, `Revert`
reproduces Balancer's exact `Error("BAL#xyz")`. In the native search, `Record`
lets one revert end one operation, not the whole run.

## How faithful it is

| Level | What it shows | Status |
|---|---|---|
| L0, isolated rounding | `mulDown(17, rate)` is 17 where 18 leaves | in the probes; not novel |
| L1, a simplified pool | the per-swap gap in a toy pool | not used: this is what earlier demonstrations did |
| **L2, the faithful kernel** | Balancer's own math and pool paths, matching the Solidity and the deployed pool exactly | **verified** |
| L3, the attacker's transaction | the real batch replayed | not done |

Two independent checks establish L2:

- **Against Balancer's Solidity** (`make differential`).
  [`StableMathDifferential.t.sol`](../contracts/reference/test/StableMathDifferential.t.sol)
  sends identical calldata to Balancer's own code, compiled with solc 0.7.6,
  and to the Fe port compiled with Fe 26.6.0. It requires the same success flag
  and byte-identical return data. Pools are drawn from four balance regimes:
  dust (where the exploit operated), small, ordinary and extreme, so both
  results and Balancer's own reverts are exercised.
  - **Result:** 22 functions, 220,000 vectors, 170,900 identical results,
    49,100 identical reverts, 0 mismatches.
  - **Sensitivity:** dropping the `+ 1` in `calc_in_given_out` makes it fail.
- **Against the deployed pool** (`make fidelity`).
  [`PoolFidelity.t.sol`](../contracts/reference/test/PoolFidelity.t.sol) forks
  Ethereum at block 23,717,399, the block before the osETH/wETH pool
  (`0xDACf5Fa1…2850c`) was drained.
  - It loads the pool's real state into the Fe contract: Vault balances,
    amplification, swap fee, actual supply (including protocol fees due), the
    last stored invariant and the rate the pool would use.
  - It then requires every quote to equal what Balancer's Vault returns for the
    same operation (`queryBatchSwap`).
  - **Result:** 330 swaps in both directions (303 values, 27 identical
    reverts) and 165 exact-out BPT exits: 495 quotes, 0 mismatches.

## Three kernels, one change

| Kernel | What it is | Where |
|---|---|---|
| Faithful | Balancer, as deployed | [`pool/faithful.fe`](../ingots/balancer_v2/src/pool/faithful.fe) |
| Typed | the same operations, amounts typed by Dimension | [`pool/typed.fe`](../ingots/balancer_v2/src/pool/typed.fe), [`pool/typed/math.fe`](../ingots/balancer_v2/src/pool/typed/math.fe) |
| Guarded | typed, plus the runtime share-value guard | [`pool/guarded.fe`](../ingots/balancer_v2/src/pool/guarded.fe) |

**The typed kernel** differs from the faithful one in exactly the two places
Balancer rounded an outgoing amount down: `swap_given_out` and
`exit_given_out`. Everything else, every StableMath call included, is
identical, and the search confirms it: the operations the types do not touch
produce identical counts.

StableMath is reached only through `typed/math.fe`, whose signatures take
`Admitted` amounts and return `Owed` ones. So Balancer's line cannot be put
back:

```
$ make show CASE=typed_pool_with_balancer_upscale
  the bug:   rejected by the compiler, error[8-0000]: type mismatch
             expected `Quantity<_, Out, Admitted>`, but `u256` is given
```

**The guarded kernel** compares the value behind each share, the invariant
divided by the supply, before and after every operation. The comparison uses an
exact 512-bit cross-multiplication. The kernel rejects any operation that
lowers that value, and on joins and exits it stores the invariant of the
balances the pool actually holds.

## What the search finds

`make explore` runs every single operation on every pool state of a grid with
both kernels and the guard, natively, in exact integers:

- 3 rates, including the wstETH rate from the incident analyses;
- 3 amplifications;
- 16 × 16 balances from 2 to 10,000;
- 2 share supplies;
- amounts up to 96.

That is 4,608 pool states and about 3.14 million operations per kernel. Two
invariants are checked: value per share must not fall, and the stored
invariant must not exceed what the actual balances support. The second is the
property the Quint model of this exploit states.

| Operation | Faithful | Typed | Guarded |
|---|---|---|---|
| exitGivenOut: value-per-share losses | 57,990 of 437,760 (worst 14.86%) | 8 (worst 0.0203%) | 0 |
| exitGivenOut: stored-invariant violations | 108,976 | 16 | 0 |
| swapGivenOut: value-per-share losses | 48 (worst 6.17%) | 0 | 0 |
| joinGivenIn: value-per-share losses | 9 (worst 0.0599%) | 9 | 0 |
| joinGivenOut: stored-invariant violations | 57 | 57 | 0 |

The typed rounding removes the losses at Balancer's two `_upscale` sites. What
remains comes from StableMath's own precision; the joins lose identically with
or without the types. The guard rejects exactly the 17 operations that would
lose, and no others.

**A greedy attacker** repeats whichever exact-out exit lowers the value per
share most, until none is possible. Gains are measured in invariant units,
which is the right measure for a stable pool:

| Pool | Faithful | Typed | Guarded |
|---|---|---|---|
| 1,000 / 1,000 wei, rate 1.21, amp 200 | attacker +20.923 | −151.416 | −151.416 |
| 8 / 8 wei, rate 1.15, amp 50 | +1.386 | −2.493 | −2.493 |
| 300 / 300 wei, rate 1.058, amp 50 | −0.743 | −95.011 | −95.011 |

`tests/explorer` pins part of the grid and one attack to exact integers on
both the EVM and the native backend, so the native numbers are tied to EVM
behaviour.

## On a real EVM

`make evm` deploys the three kernels as contracts
([`contracts.fe`](../ingots/balancer_v2/src/contracts.fe)). The typed and
guarded contracts read their rate through Dimension's banded rate boundary;
the faithful one reads it raw, as Balancer does.

- **The attack.** A greedy attacker in Foundry tries every candidate exit,
  rolls back, and keeps the worst for the pool. On 1,000 wei of each token at
  rate 1.21, over 51 exits:
  - faithful: value per share −3.38%;
  - typed and guarded: +19.51%.
- **The cost.** On a pool the size of the osETH/wETH pool before the exploit,
  10 tokens out:

| Contract | swapGivenOut gas | exitGivenOut gas | Runtime bytecode |
|---|---|---|---|
| Faithful | 15,669 | 21,116 | 7,414 B |
| Typed | 16,695 (+6.5%) | 21,478 (+1.7%) | 9,233 B |
| Guarded | 23,130 (+47.6%) | 22,313 (+5.7%) | 9,675 B |

The type machinery itself compiles away: typed and raw code produce
byte-identical bytecode at `-O1`, `-O2` and `-Os` in the probes. The typed
contract's extra cost is real work the faithful one skips: rounding up, and
checking its rate is in band on every operation.

## Limits

- One two-token pool. There are no protocol fees in the operations, and no
  Vault batching, rate cache or amplification ramp.
- The attacker's actual transaction has not been replayed (L3).
- The 288 exact-out swaps that the typed kernel refuses and Balancer accepts
  are all 1 wei out of a 2-wei rated balance. Rounded up, that wei is the whole
  scaled balance.

Reproduce: `make differential explore evm fidelity`.
