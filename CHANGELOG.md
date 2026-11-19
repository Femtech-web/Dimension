# Changelog

Changes to the `dimension` library ingot (`ingots/dimension`). Versions follow
semantic versioning; before 1.0, a minor version may change the API. Fe resolves
a git dependency's `rev` as a full commit hash, so each release lists its commit.

## 0.3.0: 2026-11-19

Commit `1171eb8339b8fc5bb6f594807f0696fde736ecaf` (tag `v0.3.0`). Release notes:
[docs/releases/v0.3.0.md](docs/releases/v0.3.0.md).

### Changed

- A balance the protocol holds is now a `Held<T>`, and a supply it issues a
  `Supply<T>`. `credit` and `debit` are methods of `Held<T>`, and `issue` and
  `retire` of `Supply<T>`, so each also checks the token, and that a holding
  is used in its role: WETH cannot be credited to a USDC balance, nor returning
  shares credited to a supply. The free functions of 0.2.0 are removed.

### Added

- `held` and `supply_of`, which read a balance or a supply from where the
  protocol keeps it. Like `given`, they are where a raw number gets its
  meaning, and `dimension check` lists each call.

## 0.2.0: 2026-11-19

Commit `468e2c20d405f1dfeaf42273e838884090d293a1` (tag `v0.2.0`). Release notes:
[docs/releases/v0.2.0.md](docs/releases/v0.2.0.md).

### Added

- `credit` and `debit`, which move a held balance, and `issue` and `retire`,
  which move a supply the protocol issues, such as its shares. Each takes only
  the direction that fits: an amount arriving can be credited, one leaving
  debited, shares going out issued, shares coming back retired. So a label is
  checked against what the code does with the money.
- `TokenUnits`, a sealed trait for the two stages in token units, `Given` and
  `Settled`. The four functions take only those, so internal 18-decimal units
  never reach a raw balance.

Nothing in 0.1.0 changes: this release only adds.

## 0.1.0: 2026-11-19

Commit `57ce4106575a173b9fc51ebb44c3c2243e285cd5` (tag `v0.1.0`). Release notes:
[docs/releases/v0.1.0.md](docs/releases/v0.1.0.md).

### Added

- `Asset`: token types and their decimals.
- `Flow` (`In`, `Out`) with `Admission`, `Obligation` and `Opposite`, and the
  stages `Given`, `Admitted`, `Owed`, `Settled`. All are sealed; `Floor` and
  `Ceil` are the only roundings.
- `Quantity` with `given`, `admit`, `owed`, `settle`, `scaled_by`, and
  `exchange` (the result moves opposite to what was given, and rounds by that
  direction).
- `ScalingFactor` and `Rate`, with `scaling_factor` (`T::DECIMALS <= 18`) and
  `with_rate`.
- `Price<B, Q>`, composed only through a shared asset.
- `Amount`, `Value<Q, V>`, `value_of`, `haircut` and `covers`, with
  `Collateral` rounding down and `Debt` up.
- `RiskPolicy`, `borrow_capacity` and `is_healthy`, whose coherence
  conditions are checked at compile time.
- `Backing` and `preserves_share_value`: an exact 512-bit share-value check.
- `value::oracle` (EVM): `Feed` and `RateSource` declarations, `verify`,
  `read` and `read_rate`, with typed errors `WrongDecimals`,
  `NonPositiveAnswer`, `StaleAnswer`, `AnswerOutOfBand` and `RateOutOfBand`.
- `value::testing`: `unsafe` `assume_price` and `assume_rate` for tests.
