<div align="center">

# Dimension

**Fe types that know which way value moves.**

[For judges](JUDGES.md) · [Verification page](docs/index.html) · [Documentation](docs/README.md) · [Results](docs/results)

[![CI](https://github.com/Femtech-web/Dimension/actions/workflows/ci.yml/badge.svg)](https://github.com/Femtech-web/Dimension/actions/workflows/ci.yml)
[![Fe 26.6.0](https://img.shields.io/badge/Fe-26.6.0-orange)](https://github.com/argotorg/fe/releases/tag/v26.6.0)
[![License](https://img.shields.io/badge/license-Apache--2.0%20%7C%20GPL--3.0-blue)](#license)

</div>

**Pitch:** Dimension is a Fe library in which the arithmetic behind two of
DeFi's costliest recent failures does not compile. Every claim it makes is
checked against the original code and the real chains.

> *"This is the only place where we round in the same direction for all
> amounts, as the impact of this rounding is expected to be minimal."*
> — Balancer V2, [`_upscale`](third_party/balancer-v2/pkg/solidity-utils/contracts/helpers/ScalingHelpers.sol)

In November 2025 that rounding drained Balancer V2's composable stable pools,
for an estimated 95 to 128 million USD. In February 2026, a Moonwell
governance proposal priced cbETH with its ETH exchange rate instead of a USD
price, and for eight days the market valued it at 1.12 USD. Both mistakes were
visible in review: one in a comment, the other in a feed's name,
`cbETHETH_ORACLE`. Neither could be enforced, because to the compiler every
number was a `u256`.

Dimension puts that meaning into Fe's types:

- an amount knows its token and which way it moves, and its rounding follows;
- a price knows its pair, and composes only through a shared asset;
- an external number becomes trusted only at a boundary that checks it.

What types cannot see, a runtime guard catches. Both incidents are reproduced
on their real code and chain state, and both are stopped.

## Two incidents, replayed

### Balancer V2: Balancer's own line, rejected by the compiler

**First, the port is Balancer.** Balancer's math and pool paths were ported to
Fe line by line:

- **Against Balancer's own Solidity:** 220,000 vectors, 0 mismatches, reverts
  included.
- **Against the deployed osETH/wETH pool:** its real state, forked at block
  23,717,399, the block before it was drained. 495 quotes, 0 mismatches.

**Then, the bug is real in it.** Over 4,608 pool states, 57,990 exact-out
exits lower the value behind each pool share (worst 14.86%). A greedy attacker
takes 20.9 invariant units from a 1,000-wei pool. Deployed on an EVM, the same
attack cuts the value per share by 3.38%.

**With Dimension, the line does not compile.** The typed pool reaches
StableMath only through signatures that demand admitted amounts. Putting
Balancer's line back is a type error:

```
$ make show CASE=typed_pool_with_balancer_upscale
  the bug:   rejected by the compiler, error[8-0000]: type mismatch
             expected `Quantity<_, Out, Admitted>`, but `u256` is given
  the fix:   -    let scaled_out = upscale(amount_out.value(), factor.value())
             +    let scaled_out = admit(amount_out, factor)
  fixed:     compiles; PASS charges_what_the_typed_pool_charges_and_more_than_balancer
```

| Same states, same attacks | Balancer (faithful port) | Typed | Typed + guard |
|---|---|---|---|
| Exact-out exits that lower value per share | 57,990 | 8 | **0** |
| Exact-out swaps that lower value per share | 48 | **0** | **0** |
| Greedy attacker on a 1,000-wei pool, invariant units | **+20.923** | −151.416 | −151.416 |
| Value per share after the attack, on an EVM | **−3.38%** | +19.51% | +19.51% |
| Gas per exact-out exit | 21,116 | 21,478 (+1.7%) | 22,313 (+5.7%) |

The types remove the losses at Balancer's two rounding sites. The 8 that
remain come from StableMath's own precision, and the guard rejects exactly
those. [The full account →](docs/balancer.md)

### Moonwell MIP-X43: 1.12 USD and 2,206.68 USD, from the same feeds

Dimension's oracle, deployed on Base forks, reads the two Chainlink feeds that
Moonwell's composite oracle combined: cbETH/ETH and ETH/USD. It multiplies
them, because the types allow nothing else:

| Base block | | Moonwell's oracle | Dimension |
|---|---|---|---|
| 42,194,662 | the last block before MIP-X43 | 2,206.68 USD | 2,206.68 USD, **identical to the wei** |
| 42,194,663 | MIP-X43 executes, 2026-02-15 18:04:33 UTC | **1.12 USD** | 2,206.68 USD |
| 11 more blocks over the next 8 days | | 1.12 USD | 2,091 to 2,243 USD |
| 42,538,949 | the fix executes, 2026-02-23 17:20:45 UTC | 2,091.16 USD | 2,091.16 USD, **identical to the wei** |

The mistake is stopped wherever it is made:

| The mistake, made as | Stopped at | By |
|---|---|---|
| MIP-X43 wrote it: the cbETH/ETH feed as cbETH's USD price | **compile time** | `expected Feed<CBETH, USD>, but Feed<CBETH, ETH> is given` |
| A registry entry that lies, with a USD feed's 8 decimals | **deployment** | the constructor checks the real feed: `WrongDecimals(feed, 8, 18)` |
| A registry entry that lies, with the real 18 decimals | **the first read** | 1.12 is outside the band declared for a USD price: `AnswerOutOfBand` |

[The on-chain record, block by block →](docs/moonwell.md)

## See it in one minute

```sh
make toolchain   # Fe 26.6.0, downloaded and checksum-verified
make demo        # both incidents: the mistake, the compiler's verdict, the fix, the evidence
```

Then `make ci` runs every offline check in about a minute, and `make fidelity`
and `make moonwell` run the fork comparisons. [JUDGES.md](JUDGES.md) is a
ten-minute tour with ways to try to break it, and
[`docs/index.html`](docs/index.html) shows every saved result on one page.

## How it works

Four layers. Each one catches what the one before cannot:

```mermaid
flowchart LR
    M["a mistake in<br/>financial arithmetic"] --> C{"compile time<br/>types, sealed traits,<br/>where predicates"}
    C -- "rejected by<br/>the compiler" --> X1(["never builds"])
    C -- "a declaration<br/>that lies" --> B{"deployment<br/>decimals checked"}
    B -- "constructor<br/>reverts" --> X2(["never deploys"])
    B --> R{"every read<br/>positive, fresh,<br/>in band"}
    R -- "reverts" --> X3(["no price"])
    R --> G{"runtime guard<br/>value per share"}
    G -- "reverts" --> X4(["no loss"])
    G --> E["what remains:<br/>a reviewed declaration"]
```

1. **Financial types.**
   - `Quantity<T, F, S>` is an amount of token `T`, moving `In` or `Out` of
     the protocol, at stage `Given`, `Admitted`, `Owed` or `Settled`. Only
     `admit` and `settle` reach the trusted stages, and they take their
     rounding from the direction. A call site never names a rounding.
   - `Price<B, Q>` composes only through a shared asset.
   - `Value<Q, V>` rounds collateral down and debt up, and the two cannot be
     added.
   - Risk policies are checked by `where` predicates. A liquidation bonus that
     would create bad debt fails to compile.
2. **Verified boundaries.** Each feed is declared once, as a typed constant
   with its pair, decimals, maximum age and band. Its decimals are checked when
   a contract binds it, and every read checks the answer is positive, fresh
   and in band.
3. **A runtime guard.** An exact 512-bit check rejects any operation that
   lowers the value behind a pool share, whatever its cause.
4. **Independent verification.** Ports are compared with the original code and
   with deployed contracts on forks. An exhaustive search runs the same kernels
   natively, and every rejected construction has a corrected twin that must
   pass.

What each layer guarantees, and what it does not:
[docs/guarantees.md](docs/guarantees.md).

## Fe highlight

**Rounding derived from meaning, enforced by the compiler, at zero runtime
cost.** A direction is a sealed trait whose associated types name its
roundings, and `admit` is the only producer of an admitted amount:

```fe
pub trait Flow: Sealed {
    /// Rounding for bringing a given amount into internal accounting.
    type Admission: Rounding
    /// Rounding for turning an internal result into an amount to transfer.
    type Obligation: Rounding
}

/// Value the protocol pays out: count at least what leaves, pay no more than owed.
impl Flow for Out {
    type Admission = Ceil
    type Obligation = Floor
}

pub fn admit<T, F: Flow>(_ q: Quantity<T, F, Given>, _ factor: ScalingFactor<T>) -> Quantity<
    T,
    F,
    Admitted,
> {
    Quantity { v: F::Admission::mul_div(q.v, factor.v, WAD) }
}
```

The direction is resolved statically. The typed code compiles to the same
bytes as hand-written `mul_div_ceil` at `-O1`, `-O2` and `-Os`, with identical
hashes recorded by the probes.

The rest of Dimension leans on Fe throughout:

| Fe feature | What Dimension does with it |
|---|---|
| Phantom generics, module-scoped privacy | Trusted values have private fields; only their checking functions construct them |
| Sealed traits with associated types | Exactly two roundings, two flows and two valuation sides; none can be added |
| `where` predicates on associated constants | Incoherent risk policies and assets over 18 decimals fail to compile |
| Const generics with bounds | One StableMath for 2 to 5 tokens (`const N: usize where N >= 2, N <= 5`) |
| Effects | A feed read needs `uses (call: mut Call, ctx: Ctx)`. Failure is an effect too: one kernel reverts with Balancer's `BAL#` codes on the EVM and records failures in a native search |
| `const fn`, `#[error]` | Feed registries are typed constants; boundary failures are typed reverts |
| The `allow_unsafe` gate | Test constructors exist, and deployable code cannot reach them (`make unsafe-policy`) |
| One source, two backends | The same kernels run as EVM contracts and as a native search, pinned to identical integers |

## Checked and attacked

| Check | Scale | Result | Run |
|---|---|---|---|
| Fe StableMath against Balancer's Solidity, on identical calldata | 22 functions, 220,000 vectors | 0 mismatches; 49,100 identical reverts | `make differential` |
| The Fe pool against the deployed pool, on a mainnet fork | 330 swaps, 165 exact-out exits | 0 mismatches | `make fidelity` |
| Exhaustive search, three kernels, exact integers | 4,608 pool states, about 3.14M operations each | the two invariants hold under the guard in every operation kind | `make explore` |
| The same kernels on the EVM and natively | pinned grid and attack | identical integers | `make unit` |
| Admission and settlement against the exact rational result | 20,000 per backend | exact floor and ceil | `make unit` |
| Constructions the compiler must reject | 16 cases, each with a corrected twin | all rejected with the intended error; all twins pass | `make compile-fail` |
| Language behaviour the design rests on | 20 probes with golden outputs and bytecode hashes | all as recorded, identical on macOS and Linux | `make probes` |
| Moonwell's market on Base forks | 14 blocks across the incident | Dimension correct at every block; identical to Moonwell where Moonwell was right | `make moonwell` |

Every run writes a report to [`docs/results/`](docs/results). Each claim in it
is a question, an answer and its evidence, and a claim that fails fails the
run.

## Try to break it

Each change below was made in a scratch copy, and the result observed:

| Change | Result |
|---|---|
| Put Balancer's `upscale` back into the typed pool | rejected by the compiler: `expected Quantity<_, Out, Admitted>` |
| Make `Out` admit with `Floor` instead of `Ceil` | the typed kernel loses exactly as Balancer did (57,990), and the attacker profits again. **The guard still stops every one:** the layers are independent |
| Drop the `+ 1` in Balancer's `calc_in_given_out` | the differential test fails on `calcInGivenOut2` and `calcInGivenOut3` |
| Declare ETH/USD with 18 decimals | the Moonwell oracle no longer deploys against the real feed |
| Add `unsafe` to a protocol ingot | `make unsafe-policy` fails CI |

## How it compares

| Prior work | What it does | What Dimension adds |
|---|---|---|
| [fe-fixedpoint](https://github.com/ridakalam52-design/fe-fixedpoint) | exact fixed-point math for Fe, with a runtime rounding mode | the rounding is decided by the type, and a wrong one does not compile |
| Balancer V3 `ScalingHelpers` | `...RoundDown` and `...RoundUp` variants, picked by the caller | the call site does not pick |
| [roundme](https://github.com/crytic/roundme), [ScType](https://conf.researchr.org/details/icse-2024/icse-2024-research-track/127/Towards-Finding-Accounting-Errors-in-Smart-Contracts) | advise on, or detect, rounding and accounting errors in Solidity | prevention at compile time, plus checked boundaries and a runtime guard |
| [Remix workshop](https://github.com/remix-project-org/remix-workshops/tree/master/RoundingDirectionExploit), [Quint model](https://github.com/informalsystems/quint-balancer-v2-rounding-bug) | teach, or model, the Balancer bug on a simplified pool | the real kernel, verified against Balancer and the deployed pool, then made unable to express the bug |

[The full comparison →](docs/comparison.md)

## Use it in your protocol

```toml
[dependencies]
dimension = { path = "../dimension/ingots/dimension" }
```

Declare your assets, type the amounts that move, declare your feeds, and let
the compiler hold the rest. [docs/guide.md](docs/guide.md) walks through each
step, with the method used to port Balancer.

## Limits

- **The Balancer kernel models one pool, not the protocol:** two tokens, no
  protocol fees in the operations, and no Vault batching, rate cache or
  amplification ramp. The attacker's own transaction is not replayed.
- **Types cannot prove an address is the feed it is declared to be.** A wrong
  feed that reports the declared decimals, with answers inside the declared
  band, passes every check.
- **The guard costs gas:** +47.6% on exact-out swaps and +5.7% on exits, so it
  is opt-in. The types alone cost +6.5% and +1.7%.
- **Rounding up refuses some dust:** 1 wei out of a 2-wei balance, which
  Balancer paid out for free.

All of them, with their evidence: [docs/guarantees.md](docs/guarantees.md).

## Build and test

Requires `make`, `curl`, Python 3.12 and [Foundry](https://getfoundry.sh)
1.4.4. The compiler is pinned to Fe 26.6.0
(`5b3f96af2ab10df11bf847551f4b81d1fe481110`) and checksum-verified into
`.tools/`; nothing uses a globally installed `fe`. The manifest is
[`fe.toml`](fe.toml), a workspace of the ingots in [`ingots/`](ingots).

| Command | What it does |
|---|---|
| `make ci` | Formatting, unsafe policy, unit, compile-fail, probes, differential, search, EVM: what CI runs |
| `make demo` | Both incidents, live |
| `make fidelity` | The Balancer port against the deployed pool (mainnet fork; `MAINNET_RPC_URL` overrides the public RPC) |
| `make moonwell` | Moonwell's market around MIP-X43 (Base forks; `BASE_RPC_URL` overrides the public RPC) |
| `make page` | Regenerates [`docs/index.html`](docs/index.html) from the saved reports |
| `make help` | Every target |

CI runs `make ci` on Linux, and the fork comparisons in a separate job.
Native executables exist for `linux_amd64` and `mac_arm64` in Fe 26.6.0;
elsewhere the native search is skipped.

## Repository layout

| Path | Contents |
|---|---|
| [`ingots/dimension`](ingots/dimension) | The library: assets, flows, roundings, prices, values, policies, the guard, the oracle boundary |
| [`ingots/balancer_v2`](ingots/balancer_v2) | Balancer V2 ported: StableMath, the faithful, typed and guarded pools, their contracts |
| [`ingots/balancer_explorer`](ingots/balancer_explorer) | The native search and greedy attacker |
| [`ingots/moonwell`](ingots/moonwell) | Moonwell's cbETH market: feed registry, composite pricing, oracle contracts |
| [`contracts/reference`](contracts/reference) | Foundry: Balancer's Solidity, the differential test, the EVM attack, both fork tests |
| [`tests`](tests) | Unit tests (EVM and native), compile-fail cases with twins, probes |
| [`scripts`](scripts) | The pinned toolchain, and one harness module per suite |
| [`third_party/balancer-v2`](third_party/balancer-v2) | Balancer's sources at the pinned commit |
| [`docs`](docs/README.md) | The documentation, the verification page and the saved results |

## Declaration

- **Pre-existing work:** none. The repository was started on 2026-11-18,
  inside the build window, after idea research on 2026-11-17.
- **Third-party code:**
  - Balancer V2's sources (GPL-3.0-or-later, commit `e91a2b6`) are vendored as
    the differential reference and translated into `ingots/balancer_v2`. Both
    keep Balancer's license; see the
    [provenance](third_party/balancer-v2/PROVENANCE.md).
  - forge-std v1.9.7 is installed at build time.
  - From Moonwell, only public deployment addresses.
  - The Remix workshop and the Quint model carry no license. They are cited,
    and nothing was copied from them.
- **AI assistance:** written with Claude Code (Anthropic) under the author's
  direction. Design, scope and every result were reviewed by the author, and
  every claim above comes from a `make` target that CI runs.

## License

Apache-2.0 ([LICENSE](LICENSE)), except `ingots/balancer_v2`,
`ingots/balancer_explorer` and `third_party/balancer-v2`. Those are
GPL-3.0-or-later as Balancer's license requires, and each carries its own
license file.
