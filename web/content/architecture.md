# Architecture

Dimension is one core ingot and two protocol demonstrations built on it, with a
verification harness around all three. This document explains how the parts fit
together and why each design choice was made. [guarantees.md](guarantees.md)
states what each part guarantees.

## Repository

```
fe.toml                      workspace: members = ["ingots/*"]
ingots/
  dimension/                 the framework (Apache-2.0)
  balancer_v2/               Balancer V2 port and its contracts (GPL-3.0-or-later)
  balancer_explorer/         native search over the Balancer kernels (GPL-3.0-or-later)
  moonwell/                  Moonwell's cbETH market priced through Dimension (Apache-2.0)
  vault/                     an ERC-4626 vault's accounting, written with Dimension (Apache-2.0)
examples/quickstart/         the project a team starts from (what `dimension new` writes)
cli/                         the command line: `new`, `check`, `feeds` (standard-library Python)
tests/
  core/  oracle/  explorer/  vault/  unit tests; core, explorer and vault run on the EVM and natively
  unsafe_root/               the one forgery the compiler allows, which `dimension check` fails
  compile_fail/              17 rejected constructions, each with a corrected twin
  zero_cost/                 typed code next to the same code by hand, measured by `make evm`
  feeds/                     wrong feed declarations that compile, for `make feeds`
  compiler_findings/         the reproducer filed as argotorg/fe#2043
  probes/                    20 language-feasibility probes on an early prototype, kept as recorded
contracts/reference/         Foundry: Balancer's Solidity, OpenZeppelin's ERC4626, every EVM or fork comparison
fixtures/balancer-v2-exploit the attacker's swaps on the pool, read from the three transactions' events
third_party/balancer-v2/     the pinned upstream sources the port is compared with
web/                         the site: renders the reports and the docs (Next.js)
scripts/
  toolchain/                 pinned, checksum-verified compiler
  reference/                 Foundry dependencies
  harness/                   one module per suite; each writes a versioned JSON report
docs/results/<suite>/        reports, one per platform
Makefile                     the only entry point; CI runs the same targets
```

Dependencies point one way. `balancer_v2`, `moonwell` and `vault` depend only
on `dimension`, `balancer_explorer` depends on `balancer_v2`, and nothing depends
on a demonstration. A new protocol module, such as a Uniswap v3 retrofit, would
be one more ingot depending on `dimension`, with no change to the core.

## The core: `ingots/dimension`

| Module | Contents |
|---|---|
| `asset` | `Asset { const DECIMALS }`, implemented once per token type |
| `rounding` | sealed `Rounding` with `Floor` and `Ceil`, the only two |
| `flow` | sealed `Flow` (`In`, `Out`) with associated `Admission` and `Obligation` roundings; sealed `Stage` (`Given`, `Admitted`, `Owed`, `Settled`); sealed `Valuation` (`Collateral` rounds down, `Debt` up) |
| `value` | `Amount<T>`, `Quantity<T, F, S>`, `Rate<T>`, `ScalingFactor<T>`, `Price<B, Q>`, `Value<Q, V>`, and the only functions that construct the trusted ones |
| `value::oracle` | EVM only: `Feed<B, Q>` and `RateSource<T>` declarations, `verify`, `read`, `read_rate` |
| `value::testing` | `unsafe fn assume_price`, `assume_rate` for tests and simulations |
| `policy` | `RiskPolicy` constants checked by `where` predicates |
| `invariant` | `Backing` and `preserves_share_value`, the runtime share-value check |

### Types carry meaning; construction carries proof

Every financial type is a phantom-typed wrapper of a `u256` with a private
field. The phantom parameters say what the number is:

- `Quantity<WSTETH, Out, Admitted>` is wstETH leaving the protocol, already
  scaled to internal units.
- `Price<CBETH, USD>` is the USD price of one cbETH.

Because the field is private, a value of a trusted type can be produced only by
the function in its module that establishes it:

| Type | Produced only by | Which establishes |
|---|---|---|
| `Quantity<_, F, Admitted>` | `admit` | the given amount rounded by `F::Admission` |
| `Quantity<_, F, Settled>` | `settle`, `scaled_by` | the result rounded by `F::Obligation` |
| `ScalingFactor<T>` | `scaling_factor` (`where T::DECIMALS <= 18`), `with_rate` | decimals in range; rate from a checked source |
| `Price<B, Q>` | `oracle::read`, `Price * Price` | a fresh, positive, in-band answer, or a composition through the shared asset |
| `Rate<T>` | `oracle::read_rate` | an in-band answer from the declared provider |
| `Value<Q, V>` | `value_of`, `haircut`, `+`, `Value::zero` | rounding by side: collateral down, debt up |

`given` and `owed` are public. They label a raw number with its direction,
which keeps entry points and math results readable. Labelling is not trusted:
nothing accepts a `Given` or `Owed` quantity where an `Admitted` or `Settled`
one is required.

Privacy in Fe is module-scoped. A child module can construct its parent's
private structs, but a sibling cannot. So the trusted types live in `value`,
and the code allowed to construct them lives in its children `value::oracle`
and `value::testing`.

### Rounding derived from direction

The rule is that a rounding error must never move value from the protocol to
whoever triggered it. `Flow` encodes it once:

| Flow | Admission (given → internal) | Obligation (internal → transfer) |
|---|---|---|
| `In`, value arriving | `Floor`: count no more than arrived | `Ceil`: charge at least what is owed |
| `Out`, value leaving | `Ceil`: count at least what leaves | `Floor`: pay no more than what is owed |

`admit` and `settle` take the rounding from `F::Admission` and
`F::Obligation`. A call site never names a direction, so it cannot name the
wrong one. `Rounding`, `Flow`, `Stage` and `Valuation` are sealed through a
private supertrait, so a third direction or a custom flow cannot be added
(compile-fail cases `custom_rounding_direction`, `custom_flow`). Static
dispatch on the type parameter means the abstraction compiles away: the probes
show byte-identical runtime bytecode against hand-written `mul_div_ceil` at
`-O1`, `-O2` and `-Os`. On the library itself, `make evm` finds the same for
Dimension's four roundings, and the same gas on every call for an ERC-4626
vault built on it (`tests/zero_cost`).

### Prices compose by type

`impl<A, B, C> Mul<Price<B, C>> for Price<A, B>` has `Output = Price<A, C>`.
cbETH/ETH times ETH/USD is cbETH/USD. cbETH/ETH times USD/ETH has no
implementation and does not compile (case `compose_prices_without_shared_asset`).

### Policies checked at compile time

`RiskPolicy` holds a market's risk parameters as associated constants. The
functions that use them state the conditions that make them coherent:

```fe
pub fn is_healthy<Q, P: RiskPolicy>(_ collateral: Value<Q, Collateral>, _ debt: Value<Q, Debt>) -> bool
where
    P::LTV_BPS < P::LIQUIDATION_THRESHOLD_BPS,
    P::LIQUIDATION_THRESHOLD_BPS * (10_000 + P::LIQUIDATION_BONUS_BPS) <= 100_000_000
```

A market whose liquidation bonus would create bad debt at the threshold fails
to compile wherever it is used (case `liquidation_bonus_creates_bad_debt`).

### Boundaries: `value::oracle`

External numbers enter through declarations made once per protocol.
`feed<B, Q>(address, decimals, max_age, min_wad, max_wad)` is a `const fn`, so
a protocol's registry is a set of typed constants, and the pair is part of the
type. Two checks apply:

- **Bind time.** `verify(feed)` checks that the feed reports the declared
  decimals. Contracts call it from their constructor.
- **Read time.** `read(feed)` requires `uses (call: mut Call, ctx: Ctx)` and
  checks that the answer is positive, not from the future, no older than
  `max_age`, and inside the band. Otherwise it reverts with a typed error
  (`WrongDecimals`, `NonPositiveAnswer`, `StaleAnswer`, `AnswerOutOfBand`,
  `RateOutOfBand`).

The checks cannot prove an address is the feed it is declared to be. For
Chainlink feeds, [`feed_check.py`](../cli/feed_check.py) checks that
before deployment, against Chainlink's directory and the chain (see
[moonwell.md](moonwell.md#before-deployment-make-feeds)).

### The runtime guard: `invariant`

`preserves_share_value(before, after)` compares `value / shares` before and
after an operation by exact 512-bit cross-multiplication (`full_mul`), so it
never rounds and never overflows. It is the layer for losses no type can see,
such as StableMath's own precision.

## Balancer V2: `ingots/balancer_v2`

```
stable/   fixed_point, math, stable_math    faithful port of Balancer's libraries
          check                             failure as an effect
pool      Pool<N>                           the state a swap, join or exit reads and writes
pool/     faithful                          Balancer's operations, rounding as Balancer does
          fees                              the protocol fees minted on joins and exits
          typed  (+ typed/math)             the same operations with Dimension's types
          guarded                           typed, with the runtime guard on
contracts                                   FaithfulPool, TypedPool, GuardedPool
harness                                     StableMathFe: 22 endpoints for the differential test
```

**The faithful port** is a line-by-line translation of the pinned Solidity
under `#![arithmetic(unchecked)]`. Balancer's own overflow and convergence
checks are kept as explicit checks with Balancer's error codes, so even reverts
can be compared byte for byte. The token count is a const generic,
`const N: usize where N >= 2, N <= 5`.

**Failure is an effect.** Every arithmetic function declares
`uses (check: mut Check)` and reports a failed check with `check.fail(...)`.
The provider decides what failing means:

- `Revert` produces Balancer's exact `Error("BAL#xyz")`, which the differential
  test compares.
- `Record` notes the failure and lets the operation unwind, so the native
  search can try millions of operations without one revert ending it.

The kernels are written once and run in both settings. Two pieces of
`#[inline(never)]` keep the Newton solvers from being inlined into every
endpoint: without them, the harness grows from 8,150 B to 11,399 B.

**The typed kernel** changes Balancer in exactly the two places it rounded an
outgoing amount down: `swap_given_out` and `exit_given_out`. Given amounts
enter through `admit` and results leave through `settle`. StableMath is reached
only through `pool/typed/math.fe`, whose signatures take `Admitted` quantities
and return `Owed` ones. Putting Balancer's `_upscale` back into the typed
kernel is therefore a type error (case `typed_pool_with_balancer_upscale`).
Routing through `math` changed no bytecode.

**Protocol fees** are ported from `ComposableStablePoolProtocolFees` and
`ExternalFees` into `pool/fees.fe`, and all three kernels pay them on every join
and exit. Before the operation, the protocol takes its share of the invariant
growth since the last join or exit. After it, it takes its share of the swap
fees the operation charged. Both are minted as BPT. Without them the faithful
kernel could not match the attack step by step: the pool minted fee BPT 33
times during the first attack transaction alone.

**The guarded kernel** runs the typed operations with `guard: true`. Each
operation reuses the invariant it already computed for the state before, taken
after the fees due are paid. On joins and exits it takes the invariant of the
balances the pool actually holds, both to store and to compute the protocol
fee, and fails with `ShareValueDecreased` if the value per share fell. The fee
on the operation itself cannot trip the guard: it is a share of the growth
beyond the fee-less invariant, so the value per share never falls by it. The
extra work is one invariant solve on swaps; on joins and exits it replaces a
solve Balancer already does.

**The contracts** keep `Pool<2>` in storage, with the osETH/wETH token layout.
`FaithfulPool` reads its rate provider unchecked, as Balancer does.
`TypedPool` and `GuardedPool` read it through `read_rate`, inside a band.

## Search: `ingots/balancer_explorer`

A native program that runs all three kernels on every single operation over a
grid of 4,608 small pool states:

- 3 rates;
- 3 amplifications;
- 16 × 16 balances;
- 2 share supplies;
- amounts up to 96.

That is about 3.14 million operations per kernel. For each it checks two
invariants with exact integers: value per share must not fall, and the stored
invariant must not exceed what the actual balances support. The second is the
property the Quint model of this exploit checks. A greedy attacker repeats the
most damaging exact-out exit. `tests/explorer` pins a small grid and one attack
to exact integers on both backends, so the native results are tied to EVM
behaviour.

## Moonwell: `ingots/moonwell`

- `registry` declares the two Chainlink feeds on Base that the cbETH market
  needs, each as a typed constant: `CBETH_ETH: Feed<CBETH, ETH>` and
  `ETH_USD: Feed<ETH, USD>`. Each `max_age` is the feed's measured heartbeat
  plus a margin.
- `pricing::ViaEth<T>` reads both legs and multiplies them into `Price<T, USD>`.
- `contracts`:
  - `CbethUsdOracle` binds both feeds in its constructor and serves `usdPrice()`.
  - `DeclaredCbethUsdFeed` deploys a single declaration given at construction,
    so the fork test can try wrong declarations against the real feed.

## The vault: `ingots/vault`

An ERC-4626 vault's accounting, as an example of Dimension in a protocol
class neither incident belongs to. Each of the four operations states which
way its given amount moves. `exchange` gives back the other token moving the
other way, rounded by that direction, so EIP-4626's four roundings need no code.
`exchange` rests on `Flow`'s associated `type Opposite: Flow`. See
[vault.md](vault.md).

## Verification

Each suite is one Python module in `scripts/harness` and one `make` target. It
writes `docs/results/<suite>/<platform>.json` with a `schema` field, the
compiler version and commit, and a list of claims. Each claim is a question,
whether it holds, and the evidence.

| Suite | What it compares | Against |
|---|---|---|
| `probes` | language behaviour and bytecode | golden diagnostics, outputs and hashes |
| `unit` | the core, the oracle boundary, the explorer | expected outputs, on the EVM and natively |
| `compile-fail` | each rejected construction, and its twin | the expected error code; the twin must pass |
| `differential` | Fe StableMath | Balancer's Solidity, identical calldata, byte-identical results |
| `explore` | three kernels | each other, and the two invariants |
| `evm` | three deployed contracts, and typed code paired with the same code by hand, at each optimization level | a greedy attacker, identical at every level; gas per operation; the pairs' results, bytes and gas |
| `vault` | the ERC-4626 vault's previews | OpenZeppelin's ERC4626 in the same states |
| `fidelity` | the faithful kernel | the deployed pool on a mainnet fork |
| `replay` | the three kernels | the attacker's own transactions, step by step, and the pool's state after each |
| `moonwell` | the Fe oracle | Moonwell's deployed oracle and the real feeds on Base forks |
| `feeds` | each declared feed | Chainlink's directory and Base; wrong declarations must be rejected |
| `consumer` | a fresh project from `dimension new` | Dimension taken by git; its tests; a misuse; `dimension check` passes it and fails it with `allow_unsafe` or a forged price |
| `mutants` | the checks themselves | realistic bugs planted one at a time; the check meant for each must fail |

Golden files never regenerate silently: `make update` rewrites them, and the
diff is reviewed before it is kept. The differential test clears Foundry's
failure cache so its counts are deterministic. CI runs `make ci` and
`make mutants` on Linux, and the fork targets, with all 17 mutants, in a
separate job. The same goldens pass on macOS and Linux,
so diagnostics and bytecode hashes do not depend on the platform.
