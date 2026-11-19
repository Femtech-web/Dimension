# Changelog

Changes to the `dimension` library ingot (`ingots/dimension`). Versions follow
semantic versioning; before 1.0, a minor version may change the API. Fe resolves
a git dependency's `rev` as a full commit hash, so each release lists its commit.

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
