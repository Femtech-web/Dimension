# Fe 26.6 feasibility probes

Before Dimension was designed, these probes checked that Fe 26.6.0 could actually
express and enforce what the design needed. They are kept unchanged as a
regression suite: `make probes` re-runs every case against the pinned compiler
and compares the output with the golden files next to each case.

`core/` is the probe library. Its constructors such as `price_unchecked` exist
only so the probes can build values; Dimension itself does not expose them.

## Cases

Rejected at compile time (`fe check` must fail with the recorded code and diagnostics):

| Case | Construction that must not compile | Error |
|---|---|---|
| `neg_wrong_quote_currency` | A cbETH/ETH price where a cbETH/USD price is required (the Moonwell MIP-X43 shape) | 8-0000 |
| `neg_invalid_price_chain` | cbETH/ETH times USD/ETH | 8-0000 |
| `neg_wrong_rounding_direction` | A rounded-up amount where a rounded-down one is required | 8-0000 |
| `neg_balancer_floor_upscale` | Balancer V2's floor `_upscale` where the operation requires ceiling rounding | 8-0000 |
| `neg_forge_private_struct` | Building a trusted price from raw fields in another ingot | 2-0003 |
| `neg_read_private_field` | Reading a trusted price's raw value in another ingot | 2-0003 |
| `neg_write_private_ledger` | Writing ledger balances directly | 2-0003 |
| `neg_forge_via_default` | Obtaining a trusted price through `core::mem::take` | 6-0003 |
| `neg_forge_via_calldata` | Decoding a trusted price straight from calldata | 9-0006 |
| `neg_implement_sealed_trait` | Posing as an approved price source from another ingot | 6-0003 |
| `neg_static_assert_decimals` | A constant contradicting an asset's declared decimals | 8-0081 |
| `neg_policy_ltv_above_threshold` | A loan-to-value above the liquidation threshold | 8-0093 |
| `neg_oracle_read_without_effects` | An oracle read whose signature omits the `Call` and `Ctx` capabilities | 8-0036 |
| `gate_unsafe_in_dependency` | Reaching `unsafe` code in a dependency the root did not allow to use it | 16-0015 |

Compile and pass:

| Case | What it shows | Backends |
|---|---|---|
| `core` | Price composition through `Mul`'s associated `Output`, typed rounding, policy predicates, the Balancer upscale edge search, and EVM-only feed checks (fresh read accepted; wrong decimals rejected at bind; an out-of-band answer rejected at read) | EVM, native |
| `pos_ledger_in_storage` | A library-owned ledger stored in another contract, mutable only through the library | EVM |
| `pos_inferred_rounding` | An unannotated `upscale` infers the ceiling rounding its consumer needs | EVM |

Documented limit:

| Case | What it shows |
|---|---|
| `bypass_unsafe_in_root` | A root ingot can forge any trusted value with a pointer cast and `unsafe`. Dimension therefore keeps protocol code in dependency ingots that are never given `allow_unsafe`, which `gate_unsafe_in_dependency` shows the compiler enforces. |

## Bytecode cost

Each pair builds the same contract twice, once with typed values and once with raw
`u256`, and compares the runtime bytecode at every optimization level.

| Pair | Operation | -O0 | -O1, -O2, -Os |
|---|---|---|---|
| `price_composition` | Compose two prices, value an amount | typed 2,207 B, raw 2,044 B | identical, 222 B |
| `ceil_upscale` | Ceiling upscale chosen by a trait type parameter vs `mul_div_ceil` | typed 2,163 B, raw 2,116 B | identical, 225 B |

These results cover these two operations only. Each Dimension kernel is benchmarked
separately rather than assumed to inherit them.

## Golden files

- `expected.diagnostics`: normalized `fe check` output for rejected cases
- `expected.<backend>.txt`: sorted `fe test` verdicts
- `expected.json`: bytecode sizes and SHA-256 per optimization level

`make probes-update` rewrites them. A changed golden means the compiler's behaviour
changed, so review the diff before keeping it. Each run writes a report to
`docs/results/probes/<platform>.json`.
