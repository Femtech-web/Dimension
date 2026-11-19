# Using Dimension

Dimension is an ordinary Fe library ingot. This guide shows how to use it in
your own protocol, one concept at a time. Each section links to the tested code
in this repository that it draws on. Snippets are quoted from that code, except
two marked as sketches, which show a pattern.

## Add the dependency

Fe 26.6 ingots depend on each other by path. Check this repository out next to
your project, then:

```toml
[dependencies]
dimension = { path = "../dimension/ingots/dimension" }
```

Never set `allow_unsafe` on this dependency in an ingot you deploy. Only test
and simulation roots need it (see [Testing](#testing)).

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
