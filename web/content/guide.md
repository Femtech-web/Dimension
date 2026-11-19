# Using Dimension

Dimension is for engineers writing DeFi contracts in Fe, and for teams porting
Solidity protocols to Fe. It is a Fe library ingot, Fe's equivalent of a Rust
crate. Your contracts depend on it, its rules are checked when they compile,
and the types themselves cost nothing at run time.

This guide covers three things:

- getting a project running with it, in five minutes;
- each concept, linked to the tested code in this repository it draws on (two
  snippets are marked as sketches of a pattern);
- a checklist for taking a protocol built on it to production.

## Requirements

- **Fe 26.6.0 or 26.7.0.** CI pins 26.6.0. On 26.7.0 every ingot also
  type-checks, and every test suite passes on the EVM and natively. Install Fe
  with its installer:
  ```sh
  curl -fsSL https://raw.githubusercontent.com/argotorg/fe/master/feup/feup.sh | bash -s -- --version v26.6.0
  ```
- **Targets.** Everything compiles for the EVM. Everything except
  `value::oracle`, which calls other contracts, also compiles natively. Fe
  26.6.0 builds native executables on Linux x86-64 and Apple silicon.

## Getting started

**1. Create a project.**

```sh
fe new my_protocol && cd my_protocol
```

**2. Add Dimension** to `fe.toml`, pinned to a release commit:

```toml
[dependencies.dimension]
source = "https://github.com/Femtech-web/Dimension"
rev = "57ce4106575a173b9fc51ebb44c3c2243e285cd5"   # v0.1.0
name = "dimension"
version = "0.1.0"
```

- Fe resolves `rev` as a full commit hash. A tag name is rejected, so take the
  commit listed for the release in the [changelog](../CHANGELOG.md).
- `name` selects the `dimension` ingot inside the repository's workspace.
- For a local checkout, use a path relative to your project; Fe rejects
  absolute paths: `dimension = { path = "../Dimension/ingots/dimension" }`.

**3. Write typed code.** Copy the quickstart's
[`src/lib.fe`](../examples/quickstart/src/lib.fe) and
[`src/tests.fe`](../examples/quickstart/src/tests.fe) into your project. They
are a deposit desk contract and its tests, and their core is this:

```fe
use dimension::{Asset, In, Out, Quantity, Settled, admit, given, owed, scaling_factor, settle}

pub struct USDC {}

impl Asset for USDC {
    const DECIMALS: u256 = 6
}

/// Internal units credited for a deposit of `raw` USDC. Value arriving is counted down.
pub fn credit(_ raw: u256) -> u256 {
    admit(given<USDC, In>(raw), scaling_factor<USDC>()).value()
}

/// USDC paid out for `internal` units owed. Value leaving is paid down.
pub fn payout(_ internal: u256) -> Quantity<USDC, Out, Settled> {
    settle(owed<USDC, Out>(internal), scaling_factor<USDC>())
}
```

**4. Check, test and build.**

```sh
fe check                     # every Dimension rule, at compile time
fe test                      # the 3 tests, on the EVM
fe test --backend native     # and natively
fe build                     # the Desk contract's bytecode and ABI, in out/
```

**5. See a rule hold.** Change `payout` to return
`Quantity<USDC, In, Settled>`, a payout treated as a charge. `fe check` rejects
it: `expected Quantity<USDC, In, Settled>, but Quantity<USDC, Out, Settled> is
given`.

All of this is checked on every CI run (`make consumer`). The quickstart is built
as a fresh project that takes Dimension by git. It must pass its tests, and a
misuse must be rejected with Dimension's type error.

For the full API, every item with its doc comment, see the reference generated
by `fe doc`: `/api` on the project site, or `make apidoc` locally.

## Declare your assets

One type per token, with its decimals. The type is how every amount, price and
value names its asset.

```fe
use dimension::Asset

pub struct USDC {}

impl Asset for USDC {
    const DECIMALS: u256 = 6
}
```

`scaling_factor<USDC>()` requires `T::DECIMALS <= 18` at compile time.

## Move amounts in and out

The pattern from the Balancer kernel
([`pool/typed.fe`](../ingots/balancer_v2/src/pool/typed.fe)) has four steps:

1. Label what the caller names with its direction.
2. Bring it into internal units with `admit`.
3. Let your math return an owed result.
4. Leave through `settle`.

The direction, `In` or `Out` of the protocol, decides every rounding. A sketch:

```fe
// 1. An amount the caller wants out of the protocol.
let wanted = given<WSTETH, Out>(17)
// 2. Admission rounds Out up: 17 wstETH at rate 1.058 counts as 18 internal units.
let scaled = admit(wanted, factor)
// 3. Your math takes admitted amounts and returns owed ones.
let charge: Quantity<WSTETH, In, Owed> = owed<WSTETH, In>(compute(scaled.value()))
// 4. Settlement rounds In up: the caller is charged at least what is owed.
let to_pay = settle(charge, factor)
```

| Flow | `admit` | `settle` |
|---|---|---|
| `In`: value arriving | rounds down | rounds up |
| `Out`: value leaving | rounds up | rounds down |

Make your math's signatures demand the stages, as
[`typed/math.fe`](../ingots/balancer_v2/src/pool/typed/math.fe) does:

```fe
pub fn bpt_in_given_exact_token_out<T, const N: usize>(
    _ pool: Pool<N>,
    _ balances: [u256; N],
    index: usize,
    amount_out: Quantity<T, Out, Admitted>,
    invariant: u256,
) -> Quantity<Bpt, In, Owed>
```

Then an amount that skipped `admit` cannot reach the math. Putting Balancer's
`_upscale` back is a compile error.

Rates come in through `ScalingFactor<T>::with_rate`, and a `Rate<T>` exists
only from a checked read (below). For a fee added to a charge or taken from a
payout, `Quantity<T, F, Settled>::scaled_by(numerator, denominator)` keeps the
direction's rounding.

## Read prices and rates at a verified boundary

Declare each feed once, with its pair as types and the bounds a sane answer
must meet. `feed` is a `const fn`, so a registry is a set of constants
([`moonwell/src/registry.fe`](../ingots/moonwell/src/registry.fe)):

```fe
use dimension::value::oracle::{Feed, feed}

pub const ETH_USD: Feed<ETH, USD> = feed(
    Address::new(0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70),
    decimals: 8,
    max_age: 1_800,
    min_wad: 100 * WAD,
    max_wad: 100_000 * WAD,
)
```

The feed is checked twice:

- **Bind it in your constructor.** `verify(ETH_USD)` checks the decimals the
  feed reports.
- **Read it with the effects it needs.** `read(ETH_USD)` requires
  `uses (call: mut Call, ctx: Ctx)` and checks that the answer is positive, not
  in the future, no older than `max_age`, and inside the band. Otherwise it
  reverts with a typed error.

Prices compose only through a shared asset
([`moonwell/src/pricing.fe`](../ingots/moonwell/src/pricing.fe)):

```fe
let cbeth_usd: Price<CBETH, USD> = oracle::read(CBETH_ETH) * oracle::read(ETH_USD)
```

Rate providers work the same way: declare `rate_source<T>(addr, min_wad:,
max_wad:)` and read it with `read_rate`, which gives a `Rate<T>`.

## Value positions and check policies

`value_of` rounds by side: collateral down, debt up
([`tests/core/src/value.fe`](../tests/core/src/value.fe)).

```fe
let collateral: Value<USD, Collateral> = value_of(Amount<ETH>::new(WAD), price)
let debt: Value<USD, Debt> = value_of(Amount<ETH>::new(WAD * 85 / 100), price)
```

A collateral value and a debt value cannot be added, and a value in USD
cannot be compared with one in ETH.

Risk parameters are constants, and the functions that use them state when
they are coherent ([`tests/core/src/policy.fe`](../tests/core/src/policy.fe)):

```fe
pub struct Conservative {}

impl RiskPolicy for Conservative {
    const LTV_BPS: u256 = 8_000
    const LIQUIDATION_THRESHOLD_BPS: u256 = 8_500
    const LIQUIDATION_BONUS_BPS: u256 = 500
}

let healthy = is_healthy<USD, Conservative>(collateral, debt)
```

A policy whose loan-to-value reaches its liquidation threshold, or whose bonus
would create bad debt at the threshold, fails to compile wherever it is used.

## Guard what types cannot see

Some losses come from precision inside your own math. Compare the value behind
each share before and after an operation. A sketch:

```fe
let before = Backing { value: invariant_before, shares: supply_before }
// ... the operation ...
let after = Backing { value: invariant_after, shares: supply_after }
assert!(preserves_share_value(before, after), "share value decreased")
```

The comparison is an exact 512-bit cross-multiplication. In the Balancer
kernel it rejects exactly the operations that would lose value, at +6.9% gas on
exits.

## Testing

Tests need prices and rates without a live feed.
`dimension::value::testing::{assume_price, assume_rate}` provide them, as
`unsafe fn`. Only a root ingot that sets `allow_unsafe = true` on its
`dimension` dependency can call them, as
[`tests/core/fe.toml`](../tests/core/fe.toml) does. Production ingots cannot.
Keep a check like `make unsafe-policy` in your CI so that stays true.

## Porting an existing protocol

The method used for Balancer, in order:

1. **Port faithfully first.** Keep the original's rounding and checks, with
   `#![arithmetic(unchecked)]` where the original wraps.
2. **Prove the port.** Compare it with the original on identical calldata, and
   with the deployed contract on a fork.
3. **Type the boundary.** Change only where amounts enter and leave, and make
   the math's signatures demand admitted amounts.
4. **Measure the difference.** Run both versions over the same states and
   attacks, and measure gas.

## Before production

A checklist for a team shipping a protocol built on Dimension:

1. **Pin a release commit**, and read the changelog before moving to another.
2. **Never set `allow_unsafe` on Dimension in an ingot you deploy.** Keep
   `assume_price` and `assume_rate` in test roots, and add a CI check like
   `make unsafe-policy`.
3. **Make your math's signatures demand admitted amounts**, as
   `typed/math.fe` does. A raw `u256` can then never reach it unrounded.
4. **Declare each feed once.** Set `max_age` from the feed's measured
   heartbeat plus a margin, and a band no honest answer leaves. Call `verify`
   in the constructor.
5. **Check every registry entry before deploying**, with
   [`feed_check.py`](../scripts/feeds/feed_check.py) for Chainlink feeds. It
   catches a wrong address that every on-chain check accepts. For other feeds,
   review address, pair and decimals against the operator's own record.
6. **Decide where the runtime guard is worth its gas.** It is one invariant
   solve on a swap, and nearly free on joins and exits.
7. **Audit as usual.** Dimension 0.1.0 is not audited. Its guarantees and
   limits are in [guarantees.md](guarantees.md).

## API at a glance

| Item | Kind | Purpose |
|---|---|---|
| `Asset` | trait | `DECIMALS` per token type |
| `In`, `Out` | flows | which way value moves; picks admission and settlement rounding |
| `Given`, `Admitted`, `Owed`, `Settled` | stages | where an amount is in its life |
| `Quantity<T, F, S>` | type | an amount of `T` moving in `F` at stage `S` |
| `given`, `owed` | functions | label a raw number |
| `admit`, `settle` | functions | the only ways to reach `Admitted` and `Settled` |
| `ScalingFactor<T>`, `scaling_factor`, `with_rate` | type, functions | decimals and rate scaling |
| `Price<B, Q>` | type | `B` priced in `Q`; `*` composes through a shared asset |
| `Rate<T>` | type | a token's exchange rate, from `read_rate` only |
| `Amount<T>`, `Value<Q, V>`, `value_of`, `haircut`, `covers` | types, functions | positions valued by side (`Collateral`, `Debt`) |
| `RiskPolicy`, `borrow_capacity`, `is_healthy` | trait, functions | risk parameters checked at compile time |
| `Backing`, `preserves_share_value` | type, function | the runtime share-value guard |
| `oracle::{feed, verify, read, rate_source, read_rate}` | EVM functions | the verified boundary |
| `testing::{assume_price, assume_rate}` | unsafe functions | test constructors |
