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
| Compile time | An amount moved against its label: credited while labelled as leaving, issued while labelled as coming back; another token's amount credited; a supply credited as if held; internal units added to a raw balance | `Held<T>` (`credit`, `debit`) and `Supply<T>` (`issue`, `retire`) take only their own token, the matching direction, in `TokenUnits` (sealed) | compile-fail cases `vault_deposit_labeled_as_leaving`, `deposit_credited_to_another_token`, `share_supply_credited_as_held`, `internal_units_credited_to_balance`; the vault and the typed pool move every balance and supply this way, the protocol's fee included, with every result unchanged; mutants | tested |
| Compile time | A third rounding direction, a custom flow, an incoherent risk policy, an asset with more than 18 decimals | sealed traits; `where` predicates on associated constants | compile-fail cases | tested |
| Compile time | Trusted values built from raw numbers; test constructors reached from production code | private fields; `unsafe fn` constructors gated by `allow_unsafe`; `make unsafe-policy` here, and `dimension check` for a team's own project | compile-fail cases `forge_price`, `forge_admitted_quantity`, `test_constructor_from_production_root`; CI policy check; `make consumer` requires `dimension check` to fail a project with `allow_unsafe` or `unsafe` code | tested |
| Compile time | An oracle read in code that has not declared it calls out and reads the clock | effects: `read` requires `uses (call: mut Call, ctx: Ctx)` | compile-fail case `oracle_read_without_effects` | tested |
| Bind time | A feed that reports different decimals than declared | `verify` in the constructor, `WrongDecimals` | oracle unit tests; on a Base fork, cbETH/ETH declared as an 8-decimal USD feed fails to deploy | verified |
| Read time | Non-positive, future, stale or out-of-band answers; out-of-band rates | `read`, `read_rate` | oracle unit tests; on a Base fork, cbETH/ETH declared as cbETH/USD fails its first read, and a stale ETH/USD leg is refused | verified |
| Runtime | An operation that lowers the value behind a pool share, whatever its cause | `preserves_share_value`, exact 512-bit comparison; `GuardedPool` | 0 losses over 3.14 million operations per kernel; rejects exactly the 17 that would lose; EVM attack; the attacker's own transactions revert; an attacker re-planning 90 swaps from the real dust state never lowers the value per share | verified |
| Review time | A Chainlink feed declared at an address that is not that pair, even one every on-chain check accepts | `cli/feed_check.py`: Chainlink's directory must list the address as the declared pair, with its decimals and a heartbeat within `max_age`, and the chain must agree | `make feeds`: Moonwell's registry passes; MIP-X43's declaration, and the cbETH/USD feed declared as ETH/USD, which every on-chain check accepts, are rejected | tested |
| External | That Chainlink's directory is right, and that `make feeds` was run before deploying | none: Chainlink's own record, and a review step | stated here | assumption |
| External | That a rate provider (`RateSource`), or a feed outside Chainlink, is what it is declared to be | none: a reviewed declaration, with no directory to check against | stated here | assumption |

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

- **That a label is true, until the money moves.** `given` and `owed` attach
  a direction to a raw number, `held` and `supply_of` a token and a role, and
  `given<T, In>(x)` compiles even if `x` is in fact leaving. Two things do not
  compile. Changing a direction after rounding: a payout cannot be used where
  a charge is required (`payout_settled_as_charge`). And moving money against
  its label: a holding takes only its own token, in the matching direction, so
  a deposit labelled as leaving cannot be credited
  (`vault_deposit_labeled_as_leaving`). In the typed Balancer pool, 17 of the
  18 labels reach a holding, and the 18th feeds StableMath, whose signature
  fixes its direction. `dimension check` lists every label for review, and
  `make consumer` requires that list to equal the compiler's.
- **That the tokens moved.** Dimension checks the books against the labels.
  That a token transfer matches each entry is the protocol's own code. The
  Balancer pool keeps balances in an array by token index, outside `Held<T>`:
  there the direction and units are typed, and `check_factor` checks at run
  time that an amount's scaling factor is the one at its index. Tokens with the
  same factor, such as two 18-decimal tokens at the same rate, are not told
  apart.
- **That StableMath is precise.** Its own rounding inside the invariant
  solvers is outside the scaling boundary. See the residuals below.
- **That no attack exists.** The recorded attack cannot run. That no other
  sequence pays rests on an attacker re-planning 90 swaps from the real dust
  state, and on every single operation over 4,608 small pools: evidence, not
  proof.
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

| Operation (gas) | Faithful | Typed | Guarded |
|---|---|---|---|
| swapGivenIn | 15,164 | 16,104 (+6.2%) | 22,644 (+49.3%) |
| swapGivenOut | 15,981 | 17,000 (+6.4%) | 23,553 (+47.4%) |
| exitGivenIn | 23,240 | 24,189 (+4.1%) | 24,995 (+7.6%) |
| exitGivenOut | 24,493 | 25,424 (+3.8%) | 26,230 (+7.1%) |
| joinGivenIn | 25,585 | 26,472 (+3.5%) | 27,278 (+6.6%) |
| joinGivenOut | 23,453 | 24,452 (+4.3%) | 25,258 (+7.7%) |

| Runtime bytecode | Faithful | Typed | Guarded |
|---|---|---|---|
| `-O0` | 19,423 B | 29,161 B | 29,167 B |
| `-O1` (default) | 8,014 B | 9,412 B | 9,867 B |
| `-O2` | 7,992 B | 9,400 B | 9,855 B |
| `-Os` | 9,139 B | 10,299 B | 10,685 B |

| Mean gas per operation | Faithful | Typed | Guarded |
|---|---|---|---|
| `-O0` | 29,850 | 32,779 (+9.8%) | 36,056 (+20.8%) |
| `-O1` (default) | 21,319 | 22,274 (+4.5%) | 24,993 (+17.2%) |
| `-O2` | 21,303 | 22,258 (+4.5%) | 24,978 (+17.3%) |
| `-Os` | 22,744 | 23,783 (+4.6%) | 26,587 (+16.9%) |

Gas is measured on a pool with the osETH/wETH pool's balances and parameters
before the exploit, including its 50% protocol swap fee, for 10 tokens or 10
BPT per operation (`make evm`). The typed contract's overhead is nearly
constant, about 800 to 1,000 gas per operation, including operations the types do
not change, such as `swapGivenIn`. It is the rate read through the banded
boundary and the factor checks, which the faithful contract does not do. The
guard's cost on swaps is one invariant solve. Started from the invariant before
the operation instead of from the balances' sum, that solve is not equivalent
at dust balances: in the search it let 13 losing operations through, so the
guard keeps Balancer's own solve ([details](balancer.md#on-a-real-evm)).

Gas is the mean over the six operations, with each contract built at that
level. Every level computes the same attack to the wei (`make evm` checks it),
so the level changes only the cost. In these contracts `-Os` gives larger code
than `-O1` and `-O2`, and 6.8% more gas than `-O2`: a compiler observation,
not a Dimension effect.

The type machinery itself is free. In the probes (`make probes`), typed and raw
code compile to byte-identical runtime bytecode at `-O1`, `-O2` and `-Os`. On
the library itself, `make evm` compares typed code with the same code written by
hand on raw `u256` ([`tests/zero_cost`](../tests/zero_cost)), calling each
function on the same 512 inputs of every magnitude at each level:

| Pair | `-O0` | `-O1` and `-O2` | `-Os` |
|---|---|---|---|
| The four roundings, for a 6-decimal token | typed 3,131 B and 3,153 gas per call; by hand 2,817 B and 2,924 (+7.8%) | identical bytes; 580 gas each | identical bytes; 601 gas each |
| An ERC-4626 vault's four previews | typed 4,034 B and 4,082 gas; by hand 3,325 B and 3,550 (+15.0%) | 671 B each, laid out differently; 740 gas each | 671 B each; 740 gas each |

Every one of the 4,096 calls per level returns the same result in both, reverts
included. `-O0` is not a level anyone deploys at.

## Fidelity of the Balancer demonstration

| Claim | Level | Status |
|---|---|---|
| FixedPoint, Math, StableMath equal Balancer's Solidity, reverts included | 22 functions, 220,000 vectors | verified |
| The pool kernel returns what the deployed osETH/wETH pool returned | 446 swap quotes and 223 exact-out BPT exits at block 23,717,396, the last before the attack | verified |
| The kernel computes the attack exactly as Balancer did | the attacker's three transactions: 360 of 360 steps equal, and every end state equal to the real pool's | verified |
| The kernel models the whole protocol | one two-token pool with protocol fees; no amplification ramp, no rate change between joins and exits, no other pools | not claimed |

## The unsafe boundary

Dimension's trust rests on protocol code living in ingots that cannot reach
`unsafe`:

- `dimension`, `balancer_v2` and `moonwell` set no `allow_unsafe`.
- The only `unsafe` in them is Dimension's test constructors in
  `value::testing`.
- `make unsafe-policy` enforces both rules in CI.

`allow_unsafe` gates what a dependency may do, not the root: a root ingot's own
`unsafe` code always compiles, and a pointer cast there can forge any value.
[`tests/unsafe_root`](../tests/unsafe_root/src/lib.fe) does it against
Dimension's own `Price`, and values collateral with the forged price, on both
backends. So `dimension check` fails any project whose sources contain `unsafe`,
read with Fe's lexical rules and confirmed against the compiler, failing if the
compiler disagrees and warning if it cannot run (`make consumer` requires it to catch exactly this forgery, also
with the strings `"/*"` and `"*/"` around it), and
`make unsafe-policy` does the same for this repository's protocol ingots.
`balancer_explorer` sets `allow_unsafe` on Dimension, because it feeds rates to
the typed kernel in simulation. It builds no contract.
