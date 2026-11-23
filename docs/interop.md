# Using Dimension from other languages

Dimension is a Fe library: its types exist while Fe compiles your code.
Other languages can still use what that code computes: Solidity calls it on
chain, JavaScript runs it in a browser, and C links it as a native library.
Each gets the same integers, to the wei, and a make target checks each one.

| Caller | How | What crosses the boundary | Checked by |
|---|---|---|---|
| Solidity, or any EVM contract | a call to the deployed Fe contract | ABI values: `uint256`, `address`, arrays | [`make live`](../scripts/harness/live.py) on Base Sepolia; every forge test |
| JavaScript | a WebAssembly module | booleans and integers up to 64 bits | [`make wasm`](../scripts/harness/wasm.py) |
| C, and anything that calls C | a native static library | `i32`, `u32`, `i64`, `u64`, `isize`, `usize`, raw pointers | [`make native`](../scripts/harness/native.py) |

## The rule at every boundary

Types are checked while code compiles, so at any boundary a value is a plain
integer again. That is true of every language: Solidity's own user-defined
value types are encoded in the ABI as the type underneath them. So Dimension
draws the line explicitly:

- **Inside Fe, the compiler enforces token, direction and rounding.** A
  contract labels each number it receives once, where it enters:
  `given<RATED, Out>(amount)` is the amount a caller asks to take out. From
  there to `.value()`, which hands the result back as a plain number, no code
  can mix tokens or directions, or round the wrong way, and still compile.
- **What a type cannot know is checked at run time, where the number
  enters.**
  - A feed's decimals are checked when the contract that binds it is deployed.
  - Each answer must be positive, not from the future, no older than its
    `max_age`, and inside its band.
  - A rate provider's rate must fall inside its band, or the read reverts
    with `RateOutOfBand`.
  - Losses no type can see, such as StableMath's own precision, are caught by
    the runtime guard in `GuardedPool`. See
    [architecture.md](architecture.md#boundaries-valueoracle).
- **The caller's own code is not checked by Fe.** A Solidity contract can
  still pass the wrong number into a call. Dimension guarantees what its code
  does with that number, not what the caller meant by it.

## From Solidity: call the contract

A Fe contract compiles to ordinary EVM bytecode with an ordinary ABI. Each
message declares its Solidity selector, as `#[selector = sol("exitGivenOut(uint256,uint256)")]`,
so Solidity calls it through an interface like any other contract. This is
how [`LiveRecorder.sol`](../contracts/reference/src/LiveRecorder.sol) ran the
attacker's batch against the Fe pools on Base Sepolia:

```solidity
interface IExitPool {
    function exitGivenOut(uint256 j, uint256 amount) external returns (uint256);
    function getRate() external view returns (uint256);
}

function run(IExitPool pool, uint256 index, uint256[] calldata amounts) external {
    for (uint256 i = 0; i < amounts.length; i++) {
        pool.exitGivenOut(index, amounts[i]);
    }
}
```

When the typed pool refuses an exit, the Solidity caller receives Balancer's
own revert, `Error("BAL#004")`, and can catch it like any other. On chain:

| What Solidity called | Outcome | Transaction |
|---|---|---|
| `FaithfulPool`, 51 exits | ran; value per BPT 1.0000 to 0.9662 | [`0x0ecf…9520`](https://sepolia.basescan.org/tx/0x0ecfa83eb8262078418123cb281fa2d1228783f83c32526e79b461fc3e6f9520) |
| `TypedPool`, the same 51 exits | reverted `BAL#004` at exit 51; value unchanged | [`0xa31a…31e2`](https://sepolia.basescan.org/tx/0xa31aece1fbc76a2df355920862d177191bfcdca4b4eb1dfd52a1bc49521231e2) |
| `CbethUsdOracle.usdPrice()` | cbETH in USD through Chainlink's feeds | [`0x03e6…eace`](https://sepolia.basescan.org/tx/0x03e65d1e49d4944e1ed75909ad9ca74f3da917a7a589fb0ff61a0c9426f6eace) |
| deploy MIP-X43's declaration: cbETH/ETH as an 8-decimal USD feed | constructor reverted `WrongDecimals` | [`0x432c…0b53`](https://sepolia.basescan.org/tx/0x432c22fcaf3be5143877b94b68194f92c7e854cd09fec74482d526d744270b53) |

`make live` reads every outcome back from the chain. Locally, every forge
test in [`contracts/reference/test`](../contracts/reference/test) does the
same: it deploys the bytecode `fe build` writes and calls it from Solidity.

**Which chains.** Any chain that runs EVM bytecode unchanged and has
Ethereum's Cancun upgrade. The newest instructions Dimension's contracts use
are `PUSH0` (Shanghai) and `MCOPY` (Cancun). To list every instruction they
use, after `make evm`:

```sh
for f in ingots/*/out/*.runtime.bin; do cast disassemble "0x$(cat "$f")"; done | awk '{print $2}' | sort -u
```

## From JavaScript: WebAssembly

Fe's WebAssembly backend compiles [`interop/kernels.fe`](../interop/kernels.fe),
bundled with Dimension and the Balancer kernels, into
[`web/public/kernels.wasm`](../web/public/kernels.wasm). A module exports the
`pub fn`s at the root of its file, and their arguments and results are
booleans and integers up to 64 bits, so the kernels return each value per BPT
as a `u64`. Loading it, as [`interop/check.mjs`](../interop/check.mjs) does:

```js
const { instance } = await WebAssembly.instantiate(fs.readFileSync("web/public/kernels.wasm"), {});
const { exits, value_after, failure } = instance.exports;
const value = BigInt.asUintN(64, value_after(1, 51)); // the typed kernel after exit 51: 0n, it fails
```

`make wasm` builds the compiler with its `wasm` feature at the pinned commit,
rebuilds the module twice to show it reproduces, and requires every value
after every exit, on every kernel, to equal forge's run of the deployed
contracts. The [live page](https://dimension-sandy.vercel.app/live) runs the
same module in your browser.

## From C: a native library

`fe build --backend native --emit staticlib` builds the functions marked
`#[unsafe(export)]` into a static library, `lib<name>.a`. An exported function
takes and returns only `i32`, `u32`, `i64`, `u64`, `isize`, `usize` and raw
pointers; the compiler rejects any other type. C, C++, Rust and Go can all
link such a library.

The same three functions the WebAssembly module exports, declared in
[`interop/check.c`](../interop/check.c):

```c
uint32_t exits(void);
uint64_t value_after(uint32_t kernel, uint32_t n);
uint32_t failure(uint32_t kernel);
```

A WebAssembly build rejects `#[unsafe(export)]`, so `make native` adds it to
those three functions when it bundles the file. Then, in a temporary
directory, it runs:

```sh
fe build --backend native --emit staticlib -O 2 kernels.fe   # writes libkernels.a
cc -O2 interop/check.c libkernels.a -o check && ./check
```

and requires the same values as `make wasm`. Fe
26.6.0 builds native code on x86-64 Linux and Apple-silicon macOS; elsewhere
`make native` is skipped and says so.

## Results

| Target | Values compared with the EVM | Report |
|---|---|---|
| WebAssembly, from JavaScript | 154, equal to the wei | [`docs/results/wasm/`](results/wasm) |
| Native library, from C | 154, equal to the wei | [`docs/results/native/`](results/native) |
| EVM, from Solidity, on Base Sepolia | every recorded outcome | [`docs/results/live/`](results/live) |

The 154 values are the value per BPT at the start and after each exit that
runs: 52 on the faithful kernel, which goes from 1.0000 to 0.9662, and 51 on
each of the typed and guarded kernels, whose exit 51 fails with `BAL#004`, as
on the EVM.
