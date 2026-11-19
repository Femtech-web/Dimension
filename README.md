# Dimension

**Pitch:** Dimension is a Fe framework that makes the arithmetic behind two of
DeFi's costliest recent failures (Balancer V2's rounding and Moonwell's oracle
pairing) impossible to write: it is rejected by the compiler, or else stopped
at a checked boundary, and every claim is verified against the original code
and the real chains.

Fe [26.6.0](https://github.com/argotorg/fe/releases/tag/v26.6.0)
(`5b3f96af2ab10df11bf847551f4b81d1fe481110`), pinned and checksum-verified.
Manifest: [`fe.toml`](fe.toml), a workspace of the ingots in [`ingots/`](ingots).

## The problem

Financial code mixes numbers that mean different things: amounts of different
tokens, prices quoted in different currencies, values moving into or out of a
protocol. To the compiler they are all `u256`, so nothing stops a rounding
direction or a price pair from being wrong:

- **Balancer V2, 2025-11-03, 95M to 128M USD by various estimates.** `_upscale`
  rounds every amount down, including amounts leaving the pool. An attacker
  batched exact-out swaps at amounts where that gap was largest, deflating the
  pool's invariant and with it the price of its shares.
- **Moonwell MIP-X43, 2026-02-15, 1.78M USD of bad debt.** A governance proposal
  gave the cbETH market the cbETH/ETH exchange rate as its USD price. For eight
  days Moonwell valued cbETH at about 1.12 USD instead of about 2,200.

Both passed review. Both are about meaning that the code never stated. Dimension
is for engineers writing or porting DeFi arithmetic in Fe who want the compiler
to hold that meaning.

## Approach

Dimension has three layers. Each one catches what the layer before cannot:

1. **Financial types.**
   - Amounts carry their asset, their direction (`In` or `Out` of the protocol)
     and their stage. Rounding is derived from the direction instead of chosen
     at each call site.
   - Prices carry their pair and compose only through a shared asset.
   - Trusted values have private fields, so they can be produced only by the
     functions that check them.
   - Risk parameters are checked at compile time by `where` predicates.
2. **Verified boundaries.**
   - Each oracle feed or rate provider is declared once, with the pair it prices.
   - When a contract binds a feed, its decimals are checked.
   - Every read checks that the answer is positive, fresh and inside a declared
     band.
   - An optional runtime guard rejects any operation that lowers the value
     behind a pool share.
3. **Independent verification.**
   - Ports are compared with the original Solidity.
   - Ports are compared with the deployed contracts on forks.
   - An exhaustive native search runs the same kernels on both backends.
   - Every compile-time rejection has a corrected twin that must compile and
     pass its tests.

Built during the contest (2026-11-03 to 24): the core ingot, a faithful Fe port
of Balancer V2's StableMath and pool paths with a typed and a guarded kernel,
the Moonwell cbETH market priced through Dimension, and the verification
harness. Every number below is produced by a `make` target and written to
[`docs/results/`](docs/results).

| Question | Answer | Reproduce |
|---|---|---|
| Does the Fe port compute exactly what Balancer's Solidity computes? | 220,000 vectors over 22 functions: 0 mismatches, reverts included | `make differential` |
| Does it compute what the deployed pool computed, on its real state the block before the exploit? | 495 quotes against `Vault.queryBatchSwap` at block 23,717,399: 0 mismatches | `make fidelity` |
| Does the faithful kernel lose value per pool share, as Balancer did? | 57,990 of 437,760 exact-out exits lose (worst 14.86%) across 4,608 pool states | `make explore` |
| Do the types alone remove the losses at Balancer's two `_upscale` sites? | swapGivenOut 48 → 0, exitGivenOut 57,990 → 8 | `make explore` |
| With the runtime guard, does any operation lose value? | 0, in every operation kind; it rejects exactly the 17 that would | `make explore` |
| Deployed on an EVM, under a greedy repeated-exit attacker? | Faithful: value per share −3.38%. Typed and guarded: +19.51% | `make evm` |
| What does the safety cost? | Typed: +1.7% gas on exits, +6.5% on exact-out swaps. Typed values alone compile to byte-identical code | `make evm`, `make probes` |
| Would Dimension have priced Moonwell's cbETH market correctly during MIP-X43? | At 12 blocks in the window: Moonwell 1.12 USD, Dimension 2,091 to 2,243 USD from the same feeds; identical to Moonwell's price, to the wei, where Moonwell was right | `make moonwell` |
| Where is MIP-X43's mistake stopped? | At compile time. If the registry itself lies, at bind time (wrong decimals) or at the first read (out of band) | `make moonwell`, `make demo` |

## Fe highlight

Rounding is derived from meaning, by the type system, at zero runtime cost.

A direction is a sealed trait whose associated types name its rounding. Only
`admit` can produce an `Admitted` amount, and it takes the rounding from the
direction:

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

The typed Balancer kernel reaches StableMath only through signatures that take
admitted amounts. Putting Balancer's own line back into it is rejected:

```
$ make show CASE=typed_pool_with_balancer_upscale
  the bug:   rejected by the compiler, error[8-0000]: type mismatch
             expected `Quantity<_, Out, Admitted>`, but `u256` is given
  the fix:   -    let scaled_out = upscale(amount_out.value(), factor.value())
             +    let scaled_out = admit(amount_out, factor)
  fixed:     compiles; PASS charges_what_the_typed_pool_charges_and_more_than_balancer
```

The direction parameter is resolved statically, so the typed code compiles to
the same bytecode as hand-written `mul_div_ceil`: byte-identical at `-O1`,
`-O2` and `-Os` ([probes](tests/probes)). Fe's effects carry the other
half: a feed read requires `uses (call: mut Call, ctx: Ctx)`, and the pool math
declares failure as an effect (`uses (check: mut Check)`). The same kernel
reverts with Balancer's `BAL#` codes on the EVM and records the failure in the
native search.

## Architecture

```
ingots/dimension            core: assets, flows, rounding, prices, values, policies, invariants   Apache-2.0
  value/oracle              EVM boundary: Chainlink feeds and rate providers
ingots/balancer_v2          Balancer V2 port: StableMath, faithful/typed/guarded pools, contracts  GPL-3.0-or-later
ingots/balancer_explorer    native exhaustive search and greedy attacker over the three kernels   GPL-3.0-or-later
ingots/moonwell             the cbETH market's feed registry, composite pricing, oracle contracts  Apache-2.0
contracts/reference         Foundry: Balancer's Solidity, differential, EVM attack, fork tests
tests/                      unit (EVM and native), compile_fail (16 cases with twins), probes (20)
scripts/harness             one Python module per suite; reports in docs/results/<suite>/<platform>.json
```

The dependency graph points one way: `balancer_v2` and `moonwell` depend on
`dimension`, and nothing depends on the demos. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the type model, the boundaries
and the verification design, and [docs/GUARANTEES.md](docs/GUARANTEES.md) for
what each layer guarantees.

## Build and test

Requires `make`, `curl`, Python 3.12 and [Foundry](https://getfoundry.sh)
1.4.4. The compiler is downloaded and checksum-verified into `.tools/`. Nothing
uses a globally installed `fe`.

```sh
make toolchain     # Fe 26.6.0 (5b3f96a), checksum-verified
make ci            # format, unsafe policy, unit, compile-fail, probes, differential, explore, evm
make fidelity      # Balancer: the port against the deployed pool on a mainnet fork
make moonwell      # Moonwell: the cbETH market on Base forks around MIP-X43
make help          # every target
```

The fork targets use public RPCs by default. Set `MAINNET_RPC_URL` or
`BASE_RPC_URL` to use your own. CI runs `make ci` on Linux, and the fork
targets in a separate job. Native executables exist for `linux_amd64` and
`mac_arm64` in Fe 26.6.0; elsewhere the native search is skipped.

## Demo

`make demo` runs both incidents live: the bug, the compiler's verdict, the fix
and the fixed code's result, then the claims the fork runs saved. For a guided
ten-minute tour, including ways to try to break it, see
[docs/JUDGES.md](docs/JUDGES.md). [`docs/index.html`](docs/index.html) renders every claim
from the saved reports on one page (`make page`). Abridged output:

```
moonwell_component_feed_in_usd_market
  incident:  Moonwell MIP-X43, 2026-02-15, about 1.78M USD bad debt
  the bug:   rejected by the compiler, error[8-0000]: type mismatch
             expected `Feed<CBETH, USD>`, but `Feed<CBETH, ETH>` is given
  the fix:   -pub const CBETH_USD: Feed<CBETH, USD> = CBETH_ETH
             +pub const CBETH_USD: ViaEth<CBETH> = ViaEth { leg: CBETH_ETH, eth_usd: ETH_USD }
  evidence:  saved by make moonwell
             holds  Where Moonwell's oracle was right, is the Fe price identical to it?
                    block 42,194,662: 2206683650838065175827 wad, block 42,538,949: 2091161605700000000000 wad, identical
```

## Limitations

- **The Balancer kernel is a model of the pool, not the whole protocol.** It is
  one two-token pool with zero protocol fees and no Vault batching, rate cache
  or amplification ramp. StableMath is verified against Balancer's Solidity.
  The pool paths are verified against the deployed pool for swaps and exact-out
  BPT exits at one block. The attacker's transaction itself is not replayed.
- **Types cannot establish oracle truth.** A registry entry is a reviewed
  declaration. A wrong feed that reports the declared decimals, with answers
  inside the declared band, passes every check.
- **Residual losses come from StableMath, not from scaling.** With types alone,
  8 exact-out exits (worst 0.0203%) and 9 exact-in joins (worst 0.0599%, the
  same in Balancer) still lose value, through StableMath's own precision. The
  runtime guard rejects exactly those. It costs +47.6% gas on exact-out swaps
  and +5.7% on exits, so it is opt-in.
- **Rounding up refuses some dust trades.** In the search, 288 exact-out swaps
  of 1 wei out of a 2-wei rated balance revert. Rounded up, that wei is the
  pool's whole scaled balance; Balancer rounded it down and paid it out for
  free.
- **`given` and `owed` are labels.** Anyone can label a raw number. What the
  types prevent is skipping the rounding step: an `Admitted` or `Settled`
  amount, a `Price` or a `Rate` can only come from the function that checks it.
- **`unsafe` in the root ingot can forge anything.** Protocol ingots never set
  `allow_unsafe`, and `make unsafe-policy` enforces it in CI.
- **The Moonwell demo checks no L2 sequencer uptime feed.**

## Declaration

- **Pre-existing work:** none. The repository was started on 2026-11-18, inside
  the build window. The design followed idea research on 2026-11-17.
- **Third-party code:**
  - Balancer V2 sources (GPL-3.0-or-later, commit `e91a2b6`) are vendored in
    [`third_party/balancer-v2`](third_party/balancer-v2) as the differential
    reference and translated into `ingots/balancer_v2`. Both keep Balancer's
    license; see its [provenance](third_party/balancer-v2/PROVENANCE.md).
  - forge-std v1.9.7 is installed at build time for the Foundry tests.
  - Moonwell: no code is reused, only public addresses from its deployment
    registry.
  - The Remix workshop and the Quint model of the Balancer bug carry no
    license. They are cited in [docs/COMPARISON.md](docs/COMPARISON.md), and
    nothing was copied from them.
- **AI assistance:** built with Claude Code (Anthropic) as a coding assistant,
  under the author's direction. It wrote code, tests, scripts and
  documentation. The author set the scope and the standards, made the design
  decisions, and reviewed and ran the results. Every claim here comes from a
  `make` target that CI runs.

## Team

<!-- TODO(author): names and links. -->

## License

Apache-2.0 ([LICENSE](LICENSE)), except `ingots/balancer_v2`,
`ingots/balancer_explorer` and `third_party/balancer-v2`. Those are
GPL-3.0-or-later as Balancer's license requires, and each carries its own
license file.
