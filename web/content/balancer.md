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
| `ComposableStablePoolProtocolFees`, `ExternalFees` | [`pool/fees.fe`](../ingots/balancer_v2/src/pool/fees.fe) | the protocol fees minted as BPT before and after every join and exit: the pool minted them 33 times in the first attack transaction, and without them only 94 of its 121 steps match (`make mutants FORKS=1`) |

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
| **L3, the attack itself** | the attacker's three transactions replayed step by step, every amount and every end state equal | **verified** |

Three independent checks establish them:

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
  Ethereum at block 23,717,396, the last block before the first attack
  transaction on the osETH/wETH pool (`0xDACf5Fa1…2850c`), which then held
  4,922 WETH and 6,851 osETH.
  - It loads the pool's real state into the Fe contract: Vault balances,
    amplification, swap fee, the 50% protocol swap fee, the actual supply (the
    protocol fees due, paid), and the osETH rate after refreshing its expired
    cache, as the pool's next swap would.
  - It then requires every quote, for amounts from 1 wei to a fifth of the
    pool, to equal what Balancer's Vault returns for the same operation
    (`queryBatchSwap`).
  - **Result:** 446 swaps in both directions (404 values, 42 identical
    reverts) and 223 exact-out BPT exits: 669 quotes, 0 mismatches.
- **Against the attack** (`make replay`): see [below](#the-attack-replayed).

## The attack, replayed

The attacker drained the pool in three transactions, in blocks 23,717,397 to
23,717,399. Each was a batch of about 120 exact-out swaps on this pool:

1. exits that bring the balances down to a few dozen wei;
2. swaps at those dust balances, where `_upscale`'s rounding is a large share
   of every amount;
3. joins that buy the pool's shares back at the deflated price.

[`extract-attack.py`](../scripts/reference/extract-attack.py) reads every swap
the Vault executed on this pool from each transaction's `Swap` events, in
order, into [`fixtures/balancer-v2-exploit`](../fixtures/balancer-v2-exploit).

[`AttackReplay.t.sol`](../contracts/reference/test/AttackReplay.t.sol) then
does the following for each transaction:

1. It forks Ethereum at that transaction.
2. It loads the pool's real state into the three Fe kernels.
3. It runs every step, naming the same amount out the attacker named.
4. It executes the real transaction on the same fork and compares the end
   states.

| Transaction | Steps | Faithful: amounts equal to Balancer's | Faithful: end state | Value per share | Typed | Guarded |
|---|---|---|---|---|---|---|
| 1, block 23,717,397 | 121 | 121 | equal | 1.0273 → 0.0202 | reverts at step 25 | reverts at step 25 |
| 2, block 23,717,398 | 121 | 121 | equal | 0.0202 → 0.000412 | reverts at step 25 | reverts at step 25 |
| 3, block 23,717,399 | 118 | 118 | equal | 0.000412 → 0.0000092 | reverts at step 22 | reverts at step 22 |

Steps are numbered from 0. "End state" means the WETH and osETH balances and the BPT supply. They are
equal to the real pool's after the real transaction, to the wei.

**On the typed kernels,** the first transaction runs like this:

1. **Steps 0 to 3** are identical to Balancer's.
2. **Steps 4 to 15**, the large exits, differ by exactly 1 wei of BPT each, in
   alternating directions. Rounding each osETH amount up shifts the invariant
   the pool stores, and with it the protocol fee on the next exit.
3. **At dust balances** the differences become large:
   - step 21 charges 73 BPT instead of 72;
   - the first two swaps charge 315,795 and 1,071,109 wei of WETH instead of
     307,353 and 625,492. 17 wei of osETH out now costs 1,071,109 wei of WETH.
4. **The plan stops fitting the pool.** The pool's balances have drifted from
   the ones the attacker computed against. Step 24 now costs the attacker 10
   wei of osETH instead of 5,182, and step 25 asks for osETH the pool does not
   hold. Balancer's own subtraction check fails (`BAL#001`), which reverts the
   batch.

Up to that point the value per share on the typed kernel had risen from 1.0273
to 1.1856: the attack was paying the pool.

What this shows, and what it does not: the attacker's own sequence cannot run
against the typed kernels. An attacker who knew the pool rounds correctly would
search for another sequence. The search and the greedy attacker below are the
evidence that none pays.

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
- **The cost.** Every operation, on a pool with the osETH/wETH pool's balances
  and parameters before the exploit, including its 50% protocol fee, 10 tokens
  or 10 BPT:

| Operation (gas) | Faithful | Typed | Guarded |
|---|---|---|---|
| swapGivenIn | 15,164 | 16,104 (+6.2%) | 22,644 (+49.3%) |
| swapGivenOut | 15,981 | 17,000 (+6.4%) | 23,553 (+47.4%) |
| exitGivenIn | 23,240 | 24,259 (+4.4%) | 25,075 (+7.9%) |
| exitGivenOut | 24,493 | 25,338 (+3.4%) | 26,154 (+6.8%) |
| joinGivenIn | 25,585 | 26,386 (+3.1%) | 27,202 (+6.3%) |
| joinGivenOut | 23,453 | 24,360 (+3.9%) | 25,176 (+7.3%) |

| Runtime bytecode | Faithful | Typed | Guarded |
|---|---|---|---|
| `-O0` | 19,423 B | 28,562 B | 28,568 B |
| `-O1` (default) | 8,014 B | 9,693 B | 10,144 B |
| `-O2` | 7,992 B | 9,675 B | 10,126 B |
| `-Os` | 9,139 B | 10,232 B | 10,616 B |

The type machinery itself compiles away: typed and raw code produce
byte-identical bytecode at `-O1`, `-O2` and `-Os` in the probes. The typed
contract's extra cost, a nearly constant 800 to 1,000 gas, is real work the
faithful one skips: reading its rate through the banded boundary and checking
its factors on every operation.

## Limits

- One two-token pool. Its operations include protocol fees, but not an
  amplification ramp, or rate changes between joins and exits. Within a
  transaction, rates cannot change after the first join or exit.
- The replay covers the attack's steps on this pool, not those on the other
  pools in the same batches.
- The 288 exact-out swaps that the typed kernel refuses and Balancer accepts
  are all 1 wei out of a 2-wei rated balance. Rounded up, that wei is the whole
  scaled balance.

Reproduce: `make differential explore evm fidelity replay`.
