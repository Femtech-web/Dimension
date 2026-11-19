# Verifying Dimension

A ten-minute path from a clean clone to every claim in the README, plus ways
to try to break it. Nothing here needs to be taken on faith: each step runs
the code and prints what it checked.

Requirements: `make`, `curl`, Python 3.12, [Foundry](https://getfoundry.sh)
1.4.4, and macOS arm64 or Linux amd64 for the native search. Times are from an
Apple-silicon laptop.

## 1. Install (about 1 minute)

```sh
make toolchain        # Fe 26.6.0 (5b3f96a), downloaded and checksum-verified into .tools/
make reference-deps   # forge-std, for the Foundry side
```

## 2. See both incidents (under 1 minute)

```sh
make demo
```

For each incident this shows:

1. the mistake, written in Fe;
2. the compiler rejecting it, which is the protection working;
3. the fix, as a diff;
4. the fixed code compiling and passing its test;
5. the claims that the fork runs saved.

- **Moonwell:** MIP-X43's configuration, written against a registry of the real
  Base feeds, is a type error. The cbETH/ETH feed is not a cbETH/USD feed.
- **Balancer:** Balancer's own `_upscale` line, put back into Dimension's typed
  pool, is a type error. StableMath only accepts amounts that went through
  `admit`.

`make show` with no argument runs all 17 compile-fail cases the same way.

## 3. Run everything offline (about 1 minute)

```sh
make ci
```

This is what CI runs on Linux. Each suite prints its claims as `holds` or
`FAILS` with the evidence, and writes a report to
`docs/results/<suite>/<platform>.json`. The lines to look for:

| Output | Means |
|---|---|
| `220000 vectors: ... 0 mismatched` | The Fe port of Balancer's StableMath equals the Solidity, reverts included |
| `holds  Do the types alone remove the losses at Balancer's two _upscale sites?` | Over 4,608 pool states: exact-out swaps 48 → 0 losing operations, exact-out exits 57,990 → 8 |
| `holds  With the runtime guard added, does any operation lose value per BPT...` | 0 in every operation kind |
| `holds  Can a repeated-exit attacker gain against the faithful kernel...` | Faithful attacker +20.923 D; with Dimension, −151.416 D |
| `holds  Deployed on an EVM, does the faithful pool let a repeated-exit attacker take value from LPs?` | The same attack against the deployed Fe contracts |
| `gas typed ... gas guarded ...` | What the safety costs per operation |

## 4. Against the real chains (about 2 minutes each, needs network)

```sh
make replay     # the attacker's three transactions, step by step (mainnet forks)
make fidelity   # Ethereum mainnet fork, block 23,717,396
make moonwell   # Base forks from block 42,194,662 to 42,538,949
```

- **`replay`** forks Ethereum at each of the attacker's three transactions. It
  replays their 360 swaps on this pool through the three Fe kernels. The
  faithful kernel must compute every amount Balancer computed, and must end in
  the state the pool reached once the real transaction runs on the same fork.
  On the typed and guarded kernels, each transaction's batch reverts. Then an
  attacker re-plans 90 swaps from the real dust state: on Balancer's
  arithmetic it cuts the value per share by 43.9%; on the typed and guarded
  kernels it never gets below where it started.
- **`fidelity`** loads the real osETH/wETH pool's state, at the last block
  before the attack, into the Fe port. It requires all 669 quotes to equal what
  Balancer's Vault returns.
- **`moonwell`** compares Moonwell's deployed oracle with Dimension's on the
  same feeds, at 14 blocks before, during and after the incident. It then tries
  MIP-X43's mistake at each layer.

Both use public RPCs. Set `MAINNET_RPC_URL` or `BASE_RPC_URL` if one is
rate-limited.

## 5. Read the code (five files)

| File | Why |
|---|---|
| [`ingots/dimension/src/flow.fe`](ingots/dimension/src/flow.fe) | The whole rounding rule, in about 60 lines |
| [`ingots/dimension/src/value.fe`](ingots/dimension/src/value.fe) | `admit` and `settle`, the only ways to produce an admitted or settled amount |
| [`ingots/balancer_v2/src/pool/typed/math.fe`](ingots/balancer_v2/src/pool/typed/math.fe) | The typed kernel's only door to StableMath |
| [`ingots/balancer_v2/src/pool/typed.fe`](ingots/balancer_v2/src/pool/typed.fe) | Compare with `faithful.fe`: the same operations, two rounding sites changed |
| [`ingots/moonwell/src/registry.fe`](ingots/moonwell/src/registry.fe) | The real Base feeds, declared once with their pairs |

## 6. Try to break it

`make mutants` (with `FORKS=1` for the last two) plants 17 realistic bugs, one at
a time, in a scratch copy, and requires the check meant for each to fail for
the reason expected of it. Its report is `docs/results/mutants/`. The changes
below are ones to try by hand; each was made in a scratch copy, and the stated
result observed.

| Change | Run | What happens |
|---|---|---|
| In `pool/typed.fe`, replace `admit(amount_out, factor)` with Balancer's `upscale(amount_out.value(), factor.value())` (importing `upscale`) | `.tools/fe-26.6.0/fe check ingots/balancer_v2` | `error[8-0000]`: expected `Quantity<_, Out, Admitted>`, but `u256` is given |
| In `dimension/src/flow.fe`, make `Out` admit with `Floor` | `make explore` | The typed kernel loses exactly as Balancer did (48 and 57,990), and the attacker profits again (+20.923 D). The runtime guard still holds: it rejects all of them. The layers are independent. |
| In `stable/stable_math.fe`, drop the `+ 1` that `calc_in_given_out` adds | `make differential` | Fails: `mismatched: calcInGivenOut2, calcInGivenOut3` |
| In `moonwell/src/registry.fe`, declare ETH/USD with 18 decimals | `make moonwell` | Fails: the oracle's constructor checks the real feed's decimals and reverts, so it never deploys ("the Fe oracle must bind the real feeds") |
| Add `unsafe { }` anywhere in `ingots/moonwell/src` | `make unsafe-policy` | Fails: unsafe code outside `dimension::value::testing` |

## Where each claim lives

| Claim | Test | Report |
|---|---|---|
| The port equals Balancer's Solidity | `contracts/reference/test/StableMathDifferential.t.sol` | `docs/results/differential/` |
| The port equals the deployed pool | `contracts/reference/test/PoolFidelity.t.sol` | `docs/results/fidelity/` |
| The port computes the attack exactly; the typed kernels stop it | `contracts/reference/test/AttackReplay.t.sol`, `fixtures/balancer-v2-exploit/` | `docs/results/replay/` |
| Types and guard remove the losses | `ingots/balancer_explorer`, pinned by `tests/explorer` on both backends | `docs/results/exploration/` |
| The attack and gas on a real EVM | `contracts/reference/test/PoolAttack.t.sol` | `docs/results/evm/` |
| Moonwell, before, during and after MIP-X43 | `contracts/reference/test/MoonwellFork.t.sol` | `docs/results/moonwell/` |
| Each rejected construction, and its fix | `tests/compile_fail/<case>/` | `docs/results/compile-fail/` |
| The type machinery is free | `tests/probes/bytecode/` | `docs/results/probes/` |

The site in [`web/`](web) shows all of these, with the replay and the Moonwell
prices charted. `make web` rebuilds it from whatever reports your runs saved.

What is and is not guaranteed, layer by layer, is in
[docs/guarantees.md](docs/guarantees.md).
